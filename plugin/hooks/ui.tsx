// Lớp giao diện của agent-stack (GĐ26): pane cây kế hoạch và lệnh /cay.
// Logic nằm ở script Python; module chỉ gọi script rồi vẽ. Lỗi ở đây không
// chạm tới hook Python: engine bỏ qua hook hỏng và chạy tiếp.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { PlanTree, PlanView } from '../types'

const PANE = 'ke-hoach'
const COMMAND = 'cay'
const CLOSED_KEY = 'planPaneClosed'
// Mã lá hay mốc của plan_tree.py (T.2, 14, 25.1.2); chặn mọi thứ khác (TM-28, TM-30).
const CODE = /^[A-Za-z0-9][A-Za-z0-9.]{0,15}$/
const TIMEOUT_MS = 10_000
const POLL_MS = 5_000
const TAG_LABEL: Record<string, string> = { ban: 'cần bạn', cho: 'chờ bên ngoài', usd: 'tốn tiền' }
// Pane tự cuộn nên hiện đủ việc của mỗi mốc, không thu gọn như widget.
const MAX_LEAVES = '200'
const EMPTY: PlanView = { tree: null, error: null, planPath: null, mtimeMs: 0 }

const plan = atom({ plugin: 'agent-stack', key: 'plan' } as const, EMPTY)

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

function paneTitle(view: PlanView): string {
  return view.tree ? `Kế hoạch · ${view.tree.project}` : 'Kế hoạch'
}

async function openPane($: EngineInterface) {
  return $.ui.open({ id: PANE, title: paneTitle(await read($, plan)) })
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

function milestoneCount(done: number | null, total: number | null): string {
  return done === null || total === null ? '' : ` (${done}/${total})`
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
    })
    $.clock.every(POLL_MS, () => poll($))
    await $.command.register({
      name: COMMAND,
      description: 'Mở pane cây kế hoạch; /cay <mã> xem một việc (vd /cay T.2)',
    })
    return started
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    // Lượt của subagent không đổi kế hoạch của phiên chính (TM-29).
    if (!e.agentId) $.clock.after(0, () => refresh($))
    return done
  })

  // Ghi nhớ lỗi thì vẫn để pane đóng như người dùng muốn.
  on('ui.close', async ($, e, next) => {
    if (e.id === PANE && e.origin.kind === 'person') await $.store.set(CLOSED_KEY, true)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('command.run', { command: COMMAND }, async ($, e) => {
    const codes = e.args.split(/[\s,]+/).filter(Boolean)
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
      <Box flexDirection="column">
        <Text dimColor wrap="wrap">
          {tree.plan} · {tree.boxes.done}/{tree.boxes.total} ô đã tick
        </Text>
        {phases.count > 0 && (
          <Text dimColor wrap="wrap">
            ✓ {phases.count} mốc xong{phases.last ? `, gần nhất: ${phases.last}` : ''}
          </Text>
        )}
        {tree.milestones.map(m => (
          <Box key={`m-${m.id}`} flexDirection="column" marginTop={1}>
            <Text bold wrap="wrap">
              {m.id} · {m.title}
              {milestoneCount(m.done, m.total)}
            </Text>
            {m.leaves.map(leaf => (
              // Nút chỉ mang mã (nút native của desktop giữ nhãn trên một dòng); chữ đầy đủ tự xuống dòng bên cạnh.
              <Box key={`l-${leaf.id}`} flexDirection="row" paddingLeft={leaf.depth * 2} gap={1}>
                <Button key={leaf.id} plain onPress={() => fillCode($, leaf.id)}>
                  {leaf.id}
                </Button>
                <Box flexGrow={1} flexShrink={1} minWidth={0}>
                  <Text wrap="wrap">
                    {leaf.full}
                    {leaf.tags.length > 0 && <Text dimColor> · {tagText(leaf.tags)}</Text>}
                  </Text>
                </Box>
              </Box>
            ))}
            {m.hidden > 0 && (
              <Text dimColor>
                +{m.hidden} việc nữa: /cay {m.id}
              </Text>
            )}
          </Box>
        ))}
        <Box marginTop={1}>
          <Text dimColor wrap="wrap">Bấm mã một việc để điền mã đó vào ô nhập.</Text>
        </Box>
      </Box>
    )
  })
}
