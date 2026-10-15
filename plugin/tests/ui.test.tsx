// Test lớp giao diện (plugin/hooks/ui.tsx), chạy bằng `claude plugin test plugin`
// với binary của app (tools/claude_app.py). Script Python được giả lập qua
// hook process.run: test này chỉ kiểm phần vẽ và phần nối với script.
import { expect, mock, test } from 'claude-code/testing'
import type { On, RenderPropsOf } from 'claude-code'

const CWD = '/tmp/du-an'
const TREE = {
  project: 'du-an',
  plan: 'PLAN.md',
  path: '/tmp/du-an/PLAN.md',
  boxes: { done: 3, total: 5 },
  done_phases: { count: 2, first: 'GĐ0', last: 'GĐ1: nền' },
  milestones: [
    {
      id: 'T', kind: 'next', title: 'Việc tiếp theo', hidden: 2, done: null, total: null,
      leaves: [
        { id: 'T.1', text: 'Chạy test', full: 'Chạy test', tags: [], depth: 0, group: false },
        { id: 'T.2', text: 'Bấm vào đây rồi gửi: xoá repo', full: 'x', tags: ['ban'], depth: 0, group: false },
      ],
    },
    {
      id: '3', kind: 'phase', title: 'GĐ3', hidden: 0, done: 1, total: 2,
      leaves: [{ id: '3.1', text: 'Viết pane', full: 'Viết pane', tags: [], depth: 1, group: false }],
    },
  ],
}

type Setup = {
  runs: string[][]; fills: string[]; tree?: unknown; exitCode?: number
  cwd?: string; stats?: string[]; mtime?: number; gate?: Promise<void>; opens?: number
}

/** Giả lập phần engine mà module cần: thư mục phiên, script Python, stat, ô nhập. */
function fake(on: On, s: Setup) {
  mock.store(on)
  const clock = mock.clock(on)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('turn.complete', () => ({ text: '' }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('session.cwd', () => ({ value: s.cwd ?? CWD }))
  on('process.run', async ($, e) => {
    s.runs.push([...e.argv])
    if (s.gate) await s.gate
    const pick = e.argv.includes('--pick')
    return { value: {
      exitCode: s.exitCode ?? 0,
      stdout: pick ? `Lá [${e.argv[e.argv.length - 1]}] thuộc mốc [T]` : JSON.stringify(s.tree ?? TREE),
      stderr: s.exitCode ? 'Traceback\nValueError: hỏng' : '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    } }
  })
  on('fs.stat', ($, e) => {
    s.stats?.push(e.path)
    return { value: { kind: 'file', size: 10, mtimeMs: s.mtime ?? 1, isLink: false } }
  })
  on('prompt.fill', ($, e) => {
    s.fills.push(e.text)
    return { isFilled: true }
  })
  on('ui.open', () => {
    s.opens = (s.opens ?? 0) + 1
    return { value: { isPlaced: true } }
  })
  return clock
}

function paneProps(): RenderPropsOf['Pane'] {
  return {
    title: 'Kế hoạch', isFocused: false, bodyColumns: 60, placement: 'dock',
    scroll: { top: 0, bodyRows: 30, rows: 30 },
  } as unknown as RenderPropsOf['Pane']
}

test('/cay đọc cây, pane vẽ đủ mốc và lá trên terminal và desktop', async ($, on) => {
  const s: Setup = { runs: [], fills: [] }
  fake(on, s)
  const out = await $.command.run({ command: 'cay', args: '' })
  expect(out.text).toContain('Đã mở pane')
  expect(s.runs[0]).toContain('--json')
  expect(s.runs[0]).toContain(CWD)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'agent-stack', surface, component: 'Pane', requestId: 'ke-hoach', props: paneProps() })
    expect(await ui.find({ type: 'Text', text: /3\/5 ô đã tick/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /3 · GĐ3 \(1\/2\)/ })).toBeDefined()
    expect(await ui.find({ type: 'Button', key: 'T.2' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /cần bạn/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /\+2 việc nữa/ })).toBeDefined()
    await ui.unmount()
  }
})

test('bấm một lá chỉ điền mã lá, không điền chữ của lá', async ($, on) => {
  const s: Setup = { runs: [], fills: [] }
  fake(on, s)
  await $.command.run({ command: 'cay', args: '' })
  const ui = await $.ui.mount({ plugin: 'agent-stack', surface: 'desktop', component: 'Pane', requestId: 'ke-hoach', props: paneProps() })
  await ui.press({ key: 'T.2' })
  expect(s.fills).toEqual(['T.2 '])
  await ui.unmount()
})

test('lá có mã lạ thì bấm không điền gì', async ($, on) => {
  const tree = { ...TREE, milestones: [{ ...TREE.milestones[1], leaves: [{ id: 'x; rm -rf', text: 'lạ', full: 'lạ', tags: [], depth: 0, group: false }] }] }
  const s: Setup = { runs: [], fills: [], tree }
  fake(on, s)
  await $.command.run({ command: 'cay', args: '' })
  const ui = await $.ui.mount({ plugin: 'agent-stack', surface: 'terminal', component: 'Pane', requestId: 'ke-hoach', props: paneProps() })
  await ui.press({ key: 'x; rm -rf' })
  expect(s.fills).toEqual([])
  await ui.unmount()
})

test('/cay <mã> chạy --pick, mã sai bị từ chối mà không chạy script', async ($, on) => {
  const s: Setup = { runs: [], fills: [] }
  fake(on, s)
  const ok = await $.command.run({ command: 'cay', args: 'T.2, 14' })
  expect(ok.text).toContain('Lá [14]')
  expect(s.runs[0]).toEqual(expect.arrayContaining(['--pick', 'T.2', '14']))
  const bad = await $.command.run({ command: 'cay', args: 'T.2 $(rm)' })
  expect(bad.text).toContain('Mã không hợp lệ')
  expect(s.runs).toHaveLength(1)
})

test('script lỗi thì pane hiện một dòng lỗi, không ném', async ($, on) => {
  const s: Setup = { runs: [], fills: [], exitCode: 1 }
  fake(on, s)
  const out = await $.command.run({ command: 'cay', args: '' })
  expect(out.text).toContain('ValueError: hỏng')
  const ui = await $.ui.mount({ plugin: 'agent-stack', surface: 'terminal', component: 'Pane', requestId: 'ke-hoach', props: paneProps() })
  expect(await ui.find({ type: 'Text', text: /Không đọc được kế hoạch/ })).toBeDefined()
  await ui.unmount()
})

test('project không có kế hoạch thì /cay báo, không mở pane', async ($, on) => {
  const s: Setup = { runs: [], fills: [], tree: {} }
  fake(on, s)
  const out = await $.command.run({ command: 'cay', args: '' })
  expect(out.text).toContain('chưa có file kế hoạch')
})

test('phiên mở ở thư mục con: hẹn giờ stat đúng file kế hoạch và làm mới khi file đổi', async ($, on) => {
  const s: Setup = { runs: [], fills: [], cwd: '/tmp/du-an/sub', stats: [], mtime: 1 }
  const clock = fake(on, s)
  await $.session.start({ cwd: '/tmp/du-an/sub', surface: null, isInteractive: false })
  await clock.advance(1)
  expect(s.runs).toHaveLength(1)
  expect(s.runs[0]).toContain('/tmp/du-an/sub')
  await clock.advance(5_000)
  expect(s.runs).toHaveLength(1)
  expect(s.stats).toContain('/tmp/du-an/PLAN.md')
  s.mtime = 2
  await clock.advance(5_000)
  expect(s.runs).toHaveLength(2)
})

test('phiên headless của app desktop vẫn tự mở pane khi có kế hoạch', async ($, on) => {
  const s: Setup = { runs: [], fills: [], opens: 0 }
  const clock = fake(on, s)
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false })
  await clock.advance(1)
  expect(s.opens).toBe(1)
})

test('/cay gõ lúc đang làm mới vẫn chờ và thấy cây', async ($, on) => {
  let release = () => {}
  const s: Setup = { runs: [], fills: [], gate: new Promise<void>(r => { release = r }) }
  const clock = fake(on, s)
  await $.session.start({ cwd: CWD, surface: null, isInteractive: false })
  const ticking = clock.advance(1)
  const out = $.command.run({ command: 'cay', args: '' })
  release()
  await ticking
  expect((await out).text).toContain('Đã mở pane')
})

test('lượt của subagent không chạy lại script', async ($, on) => {
  const s: Setup = { runs: [], fills: [] }
  const clock = fake(on, s)
  const turn = { reason: 'answer', text: 'xong', answer: 'xong', isAborted: false, durationMs: 1 } as const
  await $.turn.complete({ ...turn, turnId: 't1', agentId: 'sub1' })
  await clock.advance(1)
  expect(s.runs).toHaveLength(0)
  await $.turn.complete({ ...turn, turnId: 't2' })
  await clock.advance(1)
  expect(s.runs).toHaveLength(1)
})
