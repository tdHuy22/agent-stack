// Hợp đồng $.state của lớp giao diện (plugin/hooks/ui.tsx): dạng JSON của
// `plan_tree.py --json` (hàm public) và trạng thái pane cây kế hoạch.

export type PlanLeaf = {
  id: string
  text: string
  full: string
  tags: string[]
  depth: number
  group: boolean
}

export type PlanMilestone = {
  id: string
  kind: string
  title: string
  leaves: PlanLeaf[]
  hidden: number
  done: number | null
  total: number | null
}

export type PlanTree = {
  project: string
  plan: string
  /** Đường dẫn tuyệt đối của file kế hoạch (plan là tương đối với gốc project, không với cwd). */
  path: string
  boxes: { done: number; total: number }
  done_phases: { count: number; first: string | null; last: string | null }
  milestones: PlanMilestone[]
}

export type PlanView = {
  tree: PlanTree | null
  error: string | null
  planPath: string | null
  mtimeMs: number
}

declare module 'claude-code' {
  interface PluginState {
    // paneShown: pane Kế hoạch đã được vẽ ít nhất một lần trong phiên (giữ tới hết phiên).
    'agent-stack': { plan: PlanView; paneShown: boolean }
  }
}
