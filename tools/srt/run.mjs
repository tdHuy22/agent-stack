// Chạy một lệnh trong sandbox-runtime và in đúng một dòng JSON: mã thoát, đầu ra (đã cắt), các vi phạm quan sát được và
// việc dấu riêng (marker) của file mồi có xuất hiện trong đầu ra hay không.
// Dùng: node run.mjs <settings.json> <giây> <thư-mục-làm-việc> -- <lệnh> [đối số...]
// Môi trường của lệnh lấy từ VET_CHILD_ENV (JSON); các dạng marker cần dò lấy từ VET_MARKERS (JSON, mảng chuỗi).
// Được chép vào .cache/srt/ khi `vet.py dynamic --setup`, để import tìm thấy node_modules.
//
// Trên macOS, vi phạm đến từ `log stream` nên có độ trễ và có thể chưa sẵn sàng lúc lệnh bắt đầu. Để không báo oan,
// runner chạy một "chim hoàng yến" (đọc thư mục HOME, luôn bị chặn) TRƯỚC và SAU lệnh chính, rồi chờ tới khi thấy
// vi phạm của nó. Chim được nhận ra CHỈ bằng `command` của vi phạm (do srt gán theo lệnh, mã bị kiểm không giả được),
// kèm một nonce ngẫu nhiên mỗi lần chạy; không bao giờ dựa vào `line`, vì tên tiến trình trong đó do mã bị kiểm đặt.
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import { spawn } from 'node:child_process'
import { SandboxManager } from '@anthropic-ai/sandbox-runtime'

// Môi trường của lệnh được kiểm tra đến từ VET_CHILD_ENV (JSON). Runner giữ HOME thật của người dùng để srt hiểu đúng `~`:
// nếu truyền HOME giả cho runner thì `denyRead: ["~"]` sẽ chặn nhầm HOME giả và bỏ ngỏ HOME thật.
const childEnv = JSON.parse(process.env.VET_CHILD_ENV || '{}')
const markers = (JSON.parse(process.env.VET_MARKERS || '[]')).filter(m => typeof m === 'string' && m.length > 0)
const MAX_OUT = 20000
const CANARY_WAIT_MS = 10000
const NONCE = crypto.randomBytes(8).toString('hex')
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
const id = `vet-${process.pid}-${NONCE}`
const cap = s => (s.length > MAX_OUT ? `${s.slice(0, MAX_OUT)}\n…(đã cắt ${s.length - MAX_OUT} ký tự)` : s)
const violations = () => SandboxManager.getSandboxViolationStore().getViolations(2000)
const markOf = v => String(v.command || '')
const isCanary = v => markOf(v).includes('CANARY-') && markOf(v).includes(NONCE)

async function canary(tag) {
  const mark = `CANARY-${tag}-${NONCE}`
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
    if (violations().some(v => markOf(v).includes(mark))) return true
    await sleep(150)
  }
  return false
}

// Dò marker trên TOÀN BỘ luồng (không chỉ phần đầu bị cắt), có chừa phần đuôi để bắt marker nằm giữa hai khối.
function makeScanner() {
  const keep = Math.max(0, ...markers.map(m => m.length)) - 1
  let tail = ''
  let hit = false
  return {
    feed(chunk) {
      if (hit || markers.length === 0) return
      const text = tail + chunk.toString('latin1')
      if (markers.some(m => text.includes(m))) hit = true
      tail = keep > 0 ? text.slice(-keep) : ''
    },
    get hit() { return hit },
  }
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
  const outScan = makeScanner()
  const errScan = makeScanner()
  child.stdout.on('data', d => { outScan.feed(d); if (out.length < MAX_OUT * 2) out += d })
  child.stderr.on('data', d => { errScan.feed(d); if (err.length < MAX_OUT * 2) err += d })
  const timer = setTimeout(() => {
    timedOut = true
    try { process.kill(-child.pid, 'SIGKILL') } catch { /* đã thoát */ }
  }, Number(secs) * 1000)
  const [code, signal] = await new Promise(res => child.on('close', (c, s) => res([c, s])))
  clearTimeout(timer)
  // Diệt mọi tiến trình còn sót trong nhóm (con cháu còn chạy sau khi lệnh chính thoát). Tiến trình đã setsid() thoát khỏi
  // nhóm này; phía Python sẽ dò thêm bằng lsof trước khi quét thư mục.
  try { process.kill(-child.pid, 'SIGKILL') } catch { /* nhóm đã hết */ }
  const durationMs = Math.max(0, Date.now() - started - (timedOut ? 0 : GRACE_S * 1000)) // trừ thời gian giữ shell
  const endOk = await canary('post')
  // Runner này chỉ chạy một lệnh, nên lấy mọi vi phạm trong kho, trừ của chim hoàng yến (nhận bằng command, không bằng line).
  const lines = violations().filter(v => !isCanary(v)).map(v => String(v.line))
  const result = {
    exit: code,
    signal,
    timedOut,
    durationMs,
    stdout: cap(out),
    stderr: cap(err),
    markerInOutput: outScan.hit || errScan.hit,
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
