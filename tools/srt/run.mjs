// Chạy một lệnh trong sandbox-runtime và in đúng một dòng JSON: mã thoát, đầu ra (đã cắt) và các vi phạm quan sát được.
// Dùng: node run.mjs <settings.json> <giây> <thư-mục-làm-việc> -- <lệnh> [đối số...]
// Được chép vào .cache/srt/ khi `vet.py dynamic --setup`, để import tìm thấy node_modules.
//
// Trên macOS, vi phạm đến từ `log stream` nên có độ trễ và có thể chưa sẵn sàng lúc lệnh bắt đầu. Để không báo SẠCH oan,
// runner chạy một "chim hoàng yến" (đọc thư mục HOME, luôn bị chặn) TRƯỚC và SAU lệnh chính, rồi chờ tới khi thấy
// vi phạm của nó. Thấy chim sau nghĩa là mọi vi phạm trước đó đã về đủ; không thấy thì báo monitorOk=false.
import fs from 'node:fs'
import os from 'node:os'
import { spawn } from 'node:child_process'
import { SandboxManager } from '@anthropic-ai/sandbox-runtime'

// Môi trường của lệnh được kiểm tra đến từ VET_CHILD_ENV (JSON). Runner giữ HOME thật của người dùng để srt hiểu đúng `~`:
// nếu truyền HOME giả cho runner thì `denyRead: ["~"]` sẽ chặn nhầm HOME giả và bỏ ngỏ HOME thật.
const childEnv = JSON.parse(process.env.VET_CHILD_ENV || '{}')
const MAX_OUT = 20000
const CANARY_WAIT_MS = 10000
const [settingsPath, secs, cwd, sep, ...argv] = process.argv.slice(2)
if (sep !== '--' || argv.length === 0) {
  console.error('cách dùng: node run.mjs <settings.json> <giây> <thư-mục-làm-việc> -- <lệnh> [đối số...]')
  process.exit(2)
}

const quote = s => `'${String(s).replace(/'/g, `'\\''`)}'`
const sleep = ms => new Promise(r => setTimeout(r, ms))
const command = argv.map(quote).join(' ')
// Vi phạm của một tiến trình vừa thoát rất dễ bị mất (đo được: khoảng một nửa số lần với script chạy dưới 100 ms),
// nên giữ shell bao ngoài sống thêm một lúc rồi mới thoát, giữ nguyên mã thoát của lệnh.
const GRACE_S = 1.5
const guarded = `${command}; __ec=$?; sleep ${GRACE_S}; exit $__ec`
const id = `vet-${process.pid}-${Date.now()}`
const cap = s => (s.length > MAX_OUT ? `${s.slice(0, MAX_OUT)}\n…(đã cắt ${s.length - MAX_OUT} ký tự)` : s)
const violations = () => SandboxManager.getSandboxViolationStore().getViolations(2000)
const isCanary = v => String(v.command || '').includes('CANARY-') || String(v.line).includes('CANARY-')

async function canary(tag) {
  const mark = `CANARY-${tag}-${process.pid}-${Date.now()}`
  const cmd = `/bin/ls ${quote(os.homedir())} >/dev/null 2>&1 # ${mark}`
  const wrapped = await SandboxManager.wrapWithSandbox(cmd, undefined, undefined, undefined, {
    commandId: mark,
    commandText: cmd,
  })
  await new Promise(res => {
    const c = spawn(wrapped, { shell: true, stdio: 'ignore' })
    c.on('close', res)
    c.on('error', res)
  })
  const deadline = Date.now() + CANARY_WAIT_MS
  while (Date.now() < deadline) {
    if (violations().some(v => String(v.command || '').includes(mark) || String(v.line).includes(mark))) return true
    await sleep(150)
  }
  return false
}

async function main() {
  const config = JSON.parse(fs.readFileSync(settingsPath, 'utf8'))
  await SandboxManager.initialize(config, undefined, true)
  const startOk = await canary('pre')
  const wrapped = await SandboxManager.wrapWithSandbox(guarded, undefined, undefined, undefined, {
    commandId: id,
    commandText: command,
  })
  const started = Date.now()
  const child = spawn(wrapped, { shell: true, cwd, env: childEnv, stdio: ['ignore', 'pipe', 'pipe'], detached: true })
  let out = ''
  let err = ''
  let timedOut = false
  child.stdout.on('data', d => { if (out.length < MAX_OUT * 2) out += d })
  child.stderr.on('data', d => { if (err.length < MAX_OUT * 2) err += d })
  const timer = setTimeout(() => {
    timedOut = true
    try { process.kill(-child.pid, 'SIGKILL') } catch { /* đã thoát */ }
  }, Number(secs) * 1000)
  const [code, signal] = await new Promise(res => child.on('close', (c, s) => res([c, s])))
  clearTimeout(timer)
  const durationMs = Math.max(0, Date.now() - started - (timedOut ? 0 : GRACE_S * 1000)) // trừ thời gian giữ shell
  const endOk = await canary('post')
  // Runner này chỉ chạy một lệnh, nên lấy mọi vi phạm trong kho, trừ của chim hoàng yến.
  const lines = violations().filter(v => !isCanary(v)).map(v => String(v.line))
  const result = {
    exit: code,
    signal,
    timedOut,
    durationMs,
    stdout: cap(out),
    stderr: cap(err),
    monitorOk: startOk && endOk,
    violations: [...new Set(lines)].slice(0, 200),
  }
  process.stdout.write(`${JSON.stringify(result)}\n`)
  await SandboxManager.reset()
}

main().then(() => process.exit(0)).catch(e => {
  console.error(String((e && e.stack) || e))
  process.exit(1)
})
