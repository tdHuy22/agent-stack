// Lớp giao diện của agent-stack (GĐ26): pane cây kế hoạch và lệnh /cay.
// Logic nằm ở script Python; module chỉ gọi script rồi vẽ. Lỗi ở đây không
// chạm tới hook Python: engine bỏ qua hook hỏng và chạy tiếp.
import { atom, read, update } from 'claude-code'
import type { Color, EngineInterface, Register } from 'claude-code'

import type { PlanTree, PlanView, RouterHint } from '../types'

const PANE = 'ke-hoach'
const COMMAND = 'cay'
const RECEIPT_COMMAND = 'bien-nhan'
const RECEIPT_LINES = 15
const CLOSED_KEY = 'planPaneClosed'
// Mã lá hay mốc của plan_tree.py (T.2, 14, 25.1.2); chặn mọi thứ khác (TM-28, TM-30).
const CODE = /^[A-Za-z0-9][A-Za-z0-9.]{0,15}$/
const TIMEOUT_MS = 10_000
const POLL_MS = 5_000
// Ghi model trước hook UserPromptSubmit của Python: nhanh hay bỏ, không được giữ tin nhắn lâu (TM-36).
const PROMPT_TIMEOUT_MS = 2_000
const TAG_LABEL: Record<string, string> = { ban: 'cần bạn', cho: 'chờ bên ngoài', usd: 'tốn tiền' }
// Pane tự cuộn nên hiện đủ việc của mỗi mốc, không thu gọn như widget.
const MAX_LEAVES = '200'
const EMPTY: PlanView = { tree: null, error: null, planPath: null, mtimeMs: 0 }

const plan = atom({ plugin: 'agent-stack', key: 'plan' } as const, EMPTY)
const paneShown = atom({ plugin: 'agent-stack', key: 'paneShown' } as const, false)
const routerHint = atom({ plugin: 'agent-stack', key: 'routerHint' } as const, null as RouterHint | null)
// Giá trị đưa vào ô nhập từ dải: tên model hay mức effort (TM-37).
const SETTING = /^[a-z0-9][a-z0-9.-]{0,40}$/
const ROUTER_HINT_MS = 10 * 60_000 // cùng hạn với ROUTER_LAST_TTL của agentstack.py

// Mục system prompt cố định (TM-32): chữ là hằng, thêm từ yêu cầu đầu tiên, không phụ thuộc trạng thái pane, để
// không làm đổi system prompt giữa phiên (đổi là ghi lại cả context vào prompt cache).
const UI_SECTION = {
  id: 'agent-stack:ui',
  text:
    'agent-stack:ui. Phiên này có mod giao diện của agent-stack. Khi project có file kế hoạch, pane "Kế hoạch" cạnh ' +
    'hội thoại hiện cây kế hoạch và tự cập nhật khi file đổi; người dùng bấm mã một việc để điền mã vào ô nhập, gõ ' +
    '/cay để mở lại pane hay /cay <mã> để xem một việc. Khi luật chung bảo hiện cây kế hoạch, đừng chạy ' +
    'plan_tree.py --widget hay vẽ widget cây: thay vào đó viết một dòng nhắc xem pane Kế hoạch (hoặc gõ /cay). ' +
    'Dòng ➡️ vẫn ghi đủ như luật chung.',
  scope: 'session',
} as const

let uiEnvSet = false
// Chẩn đoán cho `/cay ?`: nơi vẽ ở lần compose gần nhất và số lần compose từ khi nạp module.
let lastSurfaces: readonly string[] | null = null
let composeCount = 0

// Lượt làm mới đang chạy: mọi bên gọi cùng chờ nó, không chạy chồng.
let inflight: Promise<void> | null = null

function script($: EngineInterface): string {
  return `${$.plugin.root}/skills/tien-do/scripts/plan_tree.py`
}

function firstLine(text: string): string {
  return (text.trim().split('\n').pop() ?? '').slice(0, 200)
}

async function mtimeOf($: EngineInterface, path: string | null): Promise<number> {
  if (!path) return 0
  try {
    return (await $.fs.stat(path)).mtimeMs
  } catch {
    return 0
  }
}

/** Chạy plan_tree.py --json cho project của phiên rồi lưu vào $.state. */
async function load($: EngineInterface): Promise<void> {
  const cwd = await $.session.cwd()
  let view: PlanView
  try {
    const run = await $.process.run(['python3', script($), '--json', '--leaves', MAX_LEAVES, '--project', cwd], {
      timeoutMs: TIMEOUT_MS,
    })
    if (run.exitCode !== 0) {
      view = { ...EMPTY, error: firstLine(run.stderr) || `plan_tree.py thoát mã ${run.exitCode}` }
    } else {
      const data = JSON.parse(run.stdout) as Partial<PlanTree>
      const tree = Array.isArray(data.milestones) ? (data as PlanTree) : null
      const planPath = tree?.path ?? null
      view = { tree, error: null, planPath, mtimeMs: await mtimeOf($, planPath) }
    }
  } catch (err) {
    view = { ...EMPTY, error: String(err).slice(0, 200) }
  }
  await update($, plan, () => view)
}

/** Làm mới cây; đang có lượt chạy thì chờ lượt đó, `fresh` thì chạy thêm một lượt sau nó. */
async function refresh($: EngineInterface, fresh = false): Promise<void> {
  if (inflight) {
    await inflight
    if (!fresh) return
  }
  while (inflight) await inflight
  inflight = load($).finally(() => {
    inflight = null
  })
  return inflight
}

/** Hẹn giờ chỉ stat file kế hoạch; chạy lại script khi file đổi (TM-29). */
async function poll($: EngineInterface): Promise<void> {
  const view = await read($, plan)
  if (!view.planPath) return
  if ((await mtimeOf($, view.planPath)) !== view.mtimeMs) await refresh($)
}

/** Ghi số liệu context và hạn mức qua ui_status.py: state/limits.json để hook UserPromptSubmit cảnh báo hạn mức
 *  cả trên app desktop (nơi statusline của terminal không chạy). `turnEnd` (sau lượt phiên chính) thì ghi thêm
 *  state/session-usage/ cho router: model, context, lúc gọi model gần nhất. Không vẽ status line: app desktop đã
 *  hiện context và hạn mức (bạn quyết 15/10/2026). */
async function recordUsage($: EngineInterface, turnEnd = false): Promise<void> {
  try {
    const usage = await $.session.usage()
    const limits: Record<string, { used_percentage: number; resets_at?: number }> = {}
    for (const w of usage.rateLimits) {
      if (w.kind !== 'five_hour' && w.kind !== 'seven_day') continue
      const resets = w.resetsAt ? Math.floor(Date.parse(w.resetsAt) / 1000) : NaN
      limits[w.kind] = Number.isFinite(resets)
        ? { used_percentage: w.percentUsed, resets_at: resets }
        : { used_percentage: w.percentUsed }
    }
    const payload = {
      session_id: await $.session.id(),
      model: { id: await $.session.model() },
      context_window: {
        used_percentage: usage.context.percent ?? null,
        total_input_tokens: usage.context.tokens ?? null,
        context_window_size: usage.context.window,
      },
      rate_limits: limits,
      turn_end: turnEnd,
    }
    await $.process.run(['python3', `${$.plugin.root}/hooks/ui_status.py`], {
      stdin: JSON.stringify(payload),
      timeoutMs: TIMEOUT_MS,
    })
  } catch {
    // Chỉ là số liệu phụ: lỗi thì cảnh báo hạn mức dùng số cũ, router quay về đọc transcript.
  }
}

/** Một dòng tóm tắt cho toast khi hook Stop của agent-stack chặn lượt (lý do đầy đủ vẫn ở transcript). */
function stopToast(reason: string): string | null {
  if (!reason.includes('agent-stack (hook Stop)')) return null
  // Neo vào cụm cố định của stop.py, không vào tên file trong lý do (tên file có thể chứa "chot-viec").
  if (reason.includes('mà chưa chạy chot-viec')) return 'agent-stack: chạy chốt việc trước khi báo xong'
  if (reason.includes('chưa đổi. Cập nhật §0')) return 'agent-stack: cập nhật §0 của file kế hoạch'
  if (reason.includes('mà người dùng chưa thấy cây kế hoạch')) return 'agent-stack: hiện cây kế hoạch cho bạn chọn việc'
  return 'agent-stack: hook Stop nhắc thêm một bước trước khi xong'
}

/** Đọc gợi ý router của tin vừa gửi (prompt_submit.py ghi, ui_status.py --router in) cho dải trên ô nhập. */
async function loadRouterHint($: EngineInterface, sessionId: string): Promise<void> {
  let hint: RouterHint | null = null
  try {
    const run = await $.process.run(['python3', `${$.plugin.root}/hooks/ui_status.py`, '--router'], {
      stdin: JSON.stringify({ session_id: sessionId }),
      timeoutMs: TIMEOUT_MS,
    })
    const data = JSON.parse(run.stdout || '{}') as Partial<RouterHint>
    if (typeof data.user === 'string' && data.user) {
      hint = {
        user: data.user.replace(/^🧭 router: /, '').slice(0, 300),
        switch: typeof data.switch === 'string' && SETTING.test(data.switch) ? data.switch : null,
        effort: typeof data.effort === 'string' && SETTING.test(data.effort) ? data.effort : null,
        loadedAt: await $.clock.now(),
      }
    }
  } catch {
    hint = null
  }
  await update($, routerHint, () => hint)
}

/** Điền lệnh vào ô nhập trống, không gửi; ô nhập đang có chữ thì chỉ nhắc, không ghi đè. */
async function fillCommand($: EngineInterface, command: string): Promise<void> {
  const box = await $.prompt.read()
  if (box.text.trim()) {
    $.ui.toast(`Xoá ô nhập rồi bấm lại, hay gõ ${command}`)
    return
  }
  const filled = await $.prompt.fill({ text: command, mode: 'replace' })
  if (!filled.isFilled) $.ui.toast(`Gõ ${command} để đổi`)
}

function paneTitle(view: PlanView): string {
  return view.tree ? `Kế hoạch · ${view.tree.project}` : 'Kế hoạch'
}

/** Mở pane; đã được vẽ thì ghi cờ paneShown cho cả phiên (mục system prompt và biến AGENT_STACK_UI dựa vào nó). */
async function openPane($: EngineInterface) {
  const opened = await $.ui.open({ id: PANE, title: paneTitle(await read($, plan)) })
  if (opened.isPlaced) await update($, paneShown, () => true)
  return opened
}

/** Điền mã việc vào ô nhập, không gửi (TM-28). */
async function fillCode($: EngineInterface, code: string): Promise<void> {
  if (!CODE.test(code)) return
  const filled = await $.prompt.fill({ text: `${code} `, mode: 'insert' })
  if (!filled.isFilled) $.ui.toast(`Gõ ${code} vào ô nhập để chọn việc này`)
}

function tagText(tags: readonly string[]): string {
  return tags.map(t => TAG_LABEL[t] ?? t).join(', ')
}

/** Thanh tiến độ bằng ký tự, vẽ được trên mọi surface: ▰▰▰▱▱▱▱▱▱▱ 3/10. */
function bar(done: number, total: number, width = 10): string {
  const filled = total > 0 ? Math.min(width, Math.max(0, Math.round((done / total) * width))) : 0
  return `${'▰'.repeat(filled)}${'▱'.repeat(width - filled)} ${done}/${total}`
}

// Viền và biểu tượng theo loại mốc, như widget của tien-do (màu là khóa theme nên hợp cả nền sáng lẫn tối).
const KIND_STYLE: Record<string, { icon: string; color: Color }> = {
  blocked: { icon: '⚠', color: 'error' },
  wip: { icon: '◐', color: 'warning' },
  next: { icon: '➜', color: 'claude' },
  phase: { icon: '●', color: 'suggestion' },
  decisions: { icon: '?', color: 'warning' },
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    // Hẹn giờ trước, đăng ký lệnh sau: đăng ký lỗi không được chặn việc làm mới cây.
    $.clock.after(0, async () => {
      await refresh($)
      const view = await read($, plan)
      // Không xét e.isInteractive: phiên của app desktop là phiên headless (isInteractive false).
      if (view.tree && !(await $.store.get(CLOSED_KEY))) await openPane($)
      $.ui.status(undefined) // xoá dòng status của bản mod cũ còn ghim lại
      await recordUsage($)
    })
    $.clock.every(POLL_MS, () => poll($))
    await $.command.register({
      name: RECEIPT_COMMAND,
      description: 'Xem biên nhận kiểm chứng của project (receipt.py show), không gọi model',
    })
    await $.command.register({
      name: COMMAND,
      description: 'Mở pane cây kế hoạch; /cay <mã> xem một việc (vd /cay T.2)',
    })
    return started
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    // Lượt của subagent không đổi kế hoạch của phiên chính (TM-29).
    if (!e.agentId) {
      // Lượt không có usage (bị ngắt trước lần gọi nào, lỗi API) không gọi model: không đóng dấu lúc gọi gần nhất.
      const called = e.usage !== undefined
      $.clock.after(0, async () => {
        await refresh($)
        await recordUsage($, called)
      })
    }
    return done
  })

  // Trước hook Python (router): ghi model hiện tại để router thấy /model đổi giữa hai lượt mà không đọc transcript.
  // Lỗi hay chậm thì bỏ qua, tin nhắn đi tiếp với `e` nguyên vẹn (TM-36).
  on('classic.UserPromptSubmit', async ($, e, next) => {
    try {
      const payload = { session_id: e.session_id, model: { id: await $.session.model() } }
      await $.process.run(['python3', `${$.plugin.root}/hooks/ui_status.py`, '--prompt'], {
        stdin: JSON.stringify(payload),
        timeoutMs: PROMPT_TIMEOUT_MS,
      })
    } catch {
      // Router quay về đọc transcript.
    }
    const result = await next(e)
    // Sau hook Python: gợi ý router của tin này đã ghi ra state; đọc ngoài lượt để tin không phải chờ.
    const sessionId = e.session_id
    $.clock.after(0, () => loadRouterHint($, sessionId))
    return result
  }).catch(($, e, next) => next(e))

  // Dải trên ô nhập: gợi ý router của tin vừa gửi, nút điền /model hay /effort khi router bảo đổi còn rẻ.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const hint = await read($, routerHint)
    // Gợi ý cũ (máy để qua đêm, đổi model bằng lệnh không qua UserPromptSubmit) thì thôi hiện.
    if (!hint || e.props.hasSurvey || (await $.clock.now()) - hint.loadedAt > ROUTER_HINT_MS) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    return (
      <Box flexDirection="row" flexWrap="wrap" gap={1}>
        <Box flexGrow={1} flexShrink={1} minWidth={0}>
          <Text color="suggestion" wrap="wrap">
            🧭 {hint.user}
          </Text>
        </Box>
        {hint.switch && (
          <Button key="router-model" onPress={() => fillCommand($, `/model ${hint.switch}`)}>
            {`/model ${hint.switch}`}
          </Button>
        )}
        {hint.effort && (
          <Button key="router-effort" onPress={() => fillCommand($, `/effort ${hint.effort}`)}>
            {`/effort ${hint.effort}`}
          </Button>
        )}
        <Button key="router-hide" plain dimColor onPress={() => update($, routerHint, () => null)}>
          Ẩn
        </Button>
      </Box>
    )
  })

  // Chỉ phiên có nơi vẽ (terminal, app desktop) và pane đã thật sự được vẽ mới thêm mục; phiên `-p` (eval) hay
  // terminal quá hẹp giữ luật cũ (vẽ widget). Cờ giữ tới hết phiên nên mục không bật tắt theo pane (TM-32).
  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    lastSurfaces = e.surfaces
    composeCount += 1
    if (e.surfaces.length === 0 || !(await read($, paneShown))) return composed
    if (!uiEnvSet) {
      uiEnvSet = true
      // Hook Python chạy sau đó (Stop) đọc biến này để thôi nhắc vẽ widget cây (TM-33).
      await $.env.set('AGENT_STACK_UI', '1')
    }
    return { sections: [...composed.sections, UI_SECTION] }
  }).catch(($, e, next) => next(e))

  // Toast chỉ báo thêm; không đổi kết quả của hook Python.
  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    const text = result.block ? stopToast(result.block) : null
    if (text) $.ui.toast(text)
    return result
  }).catch(($, e, next) => next(e))

  on('classic.StopFailure', async ($, e, next) => {
    const result = await next(e)
    $.ui.toast('agent-stack: lượt dừng vì lỗi API; lượt cuối đã được ghi lại, gõ "làm tiếp" khi sẵn sàng')
    return result
  }).catch(($, e, next) => next(e))

  // Ghi nhớ lỗi thì vẫn để pane đóng như người dùng muốn.
  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && e.origin.kind === 'person') await $.store.set(CLOSED_KEY, true)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('command.run', { command: RECEIPT_COMMAND }, async $ => {
    try {
      const cwd = await $.session.cwd()
      const run = await $.process.run(
        ['python3', `${$.plugin.root}/skills/session-keeper/scripts/receipt.py`, 'show', '--project', cwd],
        { timeoutMs: TIMEOUT_MS },
      )
      const lines = run.stdout.trim().split('\n').filter(Boolean)
      if (lines.length === 0) return { text: firstLine(run.stderr) || 'Chưa có biên nhận nào cho project này.' }
      const more = lines.length > RECEIPT_LINES ? [`… còn ${lines.length - RECEIPT_LINES} dòng: receipt.py show`] : []
      return { text: [...lines.slice(0, RECEIPT_LINES), ...more].join('\n') }
    } catch (err) {
      return { text: `Không chạy được receipt.py: ${String(err).slice(0, 200)}` }
    }
  }).catch(() => ({ text: 'Lệnh /bien-nhan gặp lỗi; xem `claude --debug`.' }))

  on('command.run', { command: COMMAND }, async ($, e) => {
    const codes = e.args.split(/[\s,]+/).filter(Boolean)
    if (codes.length === 1 && codes[0] === '?') {
      const view = await read($, plan)
      return {
        text: [
          `Kế hoạch: ${view.tree ? view.tree.plan : view.error ? `lỗi (${view.error})` : 'không có'}`,
          `Pane đã được vẽ trong phiên: ${(await read($, paneShown)) ? 'có' : 'chưa'}`,
          `Đã đóng pane bằng tay (không tự mở): ${(await $.store.get(CLOSED_KEY)) ? 'có' : 'không'}`,
          `Nơi vẽ ở lần compose gần nhất: ${lastSurfaces === null ? 'chưa có lần nào' : `[${lastSurfaces.join(', ')}]`} (${composeCount} lần)`,
          `Mục agent-stack:ui và AGENT_STACK_UI=1: ${uiEnvSet ? 'đã bật' : 'chưa bật'}`,
        ].join('\n'),
      }
    }
    if (codes.length === 0) {
      await $.store.delete(CLOSED_KEY)
      await refresh($, true)
      const view = await read($, plan)
      if (!view.tree) return { text: view.error ? `Không đọc được kế hoạch: ${view.error}` : 'Project này chưa có file kế hoạch.' }
      await openPane($)
      return { text: 'Đã mở pane Kế hoạch. Bấm mã một việc để điền mã đó vào ô nhập.' }
    }
    const bad = codes.filter(c => !CODE.test(c))
    if (bad.length > 0) return { text: `Mã không hợp lệ: ${bad.join(', ')}. Mã có dạng T.2, 14 hay 25.1.` }
    const cwd = await $.session.cwd()
    try {
      const run = await $.process.run(['python3', script($), '--project', cwd, '--pick', ...codes], {
        timeoutMs: TIMEOUT_MS,
      })
      return { text: (run.stdout.trim() || firstLine(run.stderr) || 'Không có kết quả.') }
    } catch (err) {
      return { text: `Không chạy được plan_tree.py: ${String(err).slice(0, 200)}` }
    }
  }).catch(() => ({ text: 'Lệnh /cay gặp lỗi; xem `claude --debug`.' }))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const view = await read($, plan)
    if (view.error) return <Text dimColor>Không đọc được kế hoạch: {view.error}</Text>
    const tree = view.tree
    if (!tree) return <Text dimColor>Project này chưa có file kế hoạch.</Text>

    const phases = tree.done_phases
    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold wrap="wrap">
            {tree.project} <Text dimColor>· {tree.plan}</Text>
          </Text>
          <Text color="success">{bar(tree.boxes.done, tree.boxes.total, 16)} ô đã tick</Text>
        </Box>
        {phases.count > 0 && (
          <Box borderStyle="round" borderColor="success" paddingX={1} flexDirection="column">
            <Text color="success" wrap="wrap">
              ✓ {phases.count} mốc xong
              {phases.first && phases.last ? <Text dimColor> · {phases.first} → {phases.last}</Text> : ''}
            </Text>
          </Box>
        )}
        {tree.milestones.map(m => {
          const style = KIND_STYLE[m.kind] ?? KIND_STYLE.phase!
          const own = m.leaves.filter(l => l.tags.length === 0).length
          return (
            <Box key={`m-${m.id}`} borderStyle="round" borderColor={style.color} paddingX={1} flexDirection="column">
              <Box flexDirection="row" gap={1} flexWrap="wrap">
                <Text color={style.color} bold>
                  {style.icon} {m.id}
                </Text>
                <Box flexGrow={1} flexShrink={1} minWidth={0}>
                  <Text bold wrap="wrap">
                    {m.title}
                  </Text>
                </Box>
                {m.done !== null && m.total !== null ? (
                  <Text color={style.color}>{bar(m.done, m.total)}</Text>
                ) : (
                  <Text dimColor>
                    Claude tự làm {own}/{m.leaves.length}
                    {m.hidden > 0 ? ` (+${m.hidden} chưa tải)` : ''}
                  </Text>
                )}
              </Box>
              {m.leaves.map(leaf => (
                // Nút chỉ mang mã (nút native của desktop giữ nhãn trên một dòng); chữ đầy đủ tự xuống dòng bên cạnh.
                <Box
                  key={`l-${leaf.id}`}
                  flexDirection="row"
                  paddingLeft={leaf.depth * 2}
                  gap={1}
                  marginTop={1}
                  hover={{ backgroundColor: 'subtle' }}
                >
                  <Button key={leaf.id} plain onPress={() => fillCode($, leaf.id)}>
                    {leaf.id}
                  </Button>
                  <Box flexGrow={1} flexShrink={1} minWidth={0} flexDirection="column">
                    <Text wrap="wrap">{leaf.full}</Text>
                    {leaf.tags.length > 0 ? (
                      <Text color="warning">◆ {tagText(leaf.tags)}</Text>
                    ) : (
                      <Text color="suggestion">◇ Claude làm</Text>
                    )}
                  </Box>
                </Box>
              ))}
              {m.hidden > 0 && (
                <Text dimColor>
                  +{m.hidden} việc nữa: /cay {m.id}
                </Text>
              )}
            </Box>
          )
        })}
        <Text dimColor wrap="wrap">
          Bấm mã một việc để điền mã đó vào ô nhập.
        </Text>
      </Box>
    )
  })
}
