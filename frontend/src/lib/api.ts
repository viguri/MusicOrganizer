const API_BASE = "/api"

export type GenreGroupingMode = "backend" | "openai" | "ollama"

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// --- Health ---
export const getHealth = () => request<{ status: string; version: string }>("/health")
export const getConfig = () =>
  request<{
    styles_dir: string
    new_releases_dir: string
    master_collection: string
    target_folder_count: number
  }>("/config")

// --- Scan ---
export const startScan = (directory: string, save_to_db = true, recursive = true) =>
  request<{ task_id: string; status: string; directory: string }>("/scan/start", {
    method: "POST",
    body: JSON.stringify({ directory, save_to_db, recursive }),
  })

export const analyzeGenres = (
  directory: string,
  use_embeddings = true,
  target_folders = 50,
  recursive = true,
  grouping_mode: GenreGroupingMode = "backend"
) =>
  request<{ task_id: string; status: string }>("/scan/analyze-genres", {
    method: "POST",
    body: JSON.stringify({
      directory,
      use_embeddings,
      grouping_mode,
      use_openai: grouping_mode === "openai",
      target_folders,
      recursive,
    }),
  })

export const getTaskStatus = (task_id: string) =>
  request<{ status: string; type: string; result?: Record<string, unknown>; error?: string }>(
    `/scan/task/${task_id}`
  )

export const getSummary = () =>
  request<Record<string, unknown>>("/scan/summary")

export const getGenreStats = () =>
  request<Record<string, unknown>>("/scan/genre-stats")

export const getFolderMapping = () =>
  request<Record<string, string[]>>("/scan/folder-mapping")

export const getLabelMapping = () =>
  request<Record<string, string>>("/scan/label-mapping")

// --- Organize ---
export const planOrganize = (source: string, dest: string, recursive = true) =>
  request<{ task_id: string; status: string }>("/organize/plan", {
    method: "POST",
    body: JSON.stringify({ source, dest, dry_run: true, recursive }),
  })

export const executePlan = (plan_id: string) =>
  request<{ task_id: string; status: string; files_to_move: number }>(
    `/organize/execute/${plan_id}`,
    { method: "POST" }
  )

export const updatePlanFolders = (plan_id: string, overrides: Record<string, string>) =>
  request<{ status: string; result: Record<string, unknown> }>(`/organize/plan/${plan_id}/folders`, {
    method: "POST",
    body: JSON.stringify({ overrides }),
  })

export const rollbackMoves = (rollback_log: string) =>
  request<Record<string, unknown>>("/organize/rollback", {
    method: "POST",
    body: JSON.stringify({ rollback_log }),
  })

export const cleanNames = (directory: string, dry_run = true) =>
  request<{ task_id: string; status: string }>("/organize/clean-names", {
    method: "POST",
    body: JSON.stringify({ directory, dry_run }),
  })

export const scanDuplicates = (source: string, against?: string) =>
  request<{ task_id: string; status: string }>("/organize/duplicates", {
    method: "POST",
    body: JSON.stringify({ source, against }),
  })

export const deleteDuplicates = (task_id: string, use_hash = true, use_metadata = false, dry_run = true) =>
  request<{
    dry_run: boolean
    total_to_delete: number
    total_deleted: number
    total_errors: number
    files_to_delete: Array<{ path: string; reason: string; type: string }>
    errors: Array<{ path: string; reason: string; type: string; error: string }>
  }>(`/organize/duplicates/${task_id}/delete`, {
    method: "POST",
    body: JSON.stringify({ use_hash, use_metadata, dry_run }),
  })

export const moveDuplicates = (
  task_id: string,
  destination_folder: string,
  use_hash = true,
  use_metadata = false,
  dry_run = true,
  preserve_structure = true
) =>
  request<{
    dry_run: boolean
    total_to_move: number
    total_moved: number
    total_errors: number
    files_to_move: Array<{ path: string; reason: string; type: string; destination?: string }>
    errors: Array<{ path: string; reason: string; type: string; error: string }>
    destination_folder: string | null
  }>(`/organize/duplicates/${task_id}/move`, {
    method: "POST",
    body: JSON.stringify({ destination_folder, use_hash, use_metadata, dry_run, preserve_structure }),
  })

export const listDuplicateScans = (limit = 20) =>
  request<{
    scans: Array<{
      id: string
      source_dir: string
      against_dir: string | null
      total_hash_groups: number
      total_hash_files: number
      total_meta_groups: number
      total_meta_files: number
      created_at: string
    }>
  }>(`/organize/duplicates/scans?limit=${limit}`)

export const getDuplicateScan = (scan_id: string) =>
  request<Record<string, unknown>>(`/organize/duplicates/${scan_id}`)

export const deleteDuplicateScanRecord = (scan_id: string) =>
  request<{ status: string; scan_id: string }>(`/organize/duplicates/${scan_id}`, {
    method: "DELETE",
  })

export const getOrganizeTaskStatus = (task_id: string) =>
  request<{ status: string; type: string; result?: Record<string, unknown>; error?: string }>(
    `/organize/task/${task_id}`
  )

export const createFolders = (dest: string) =>
  request<{ status: string; folders_in_mapping: number }>(
    `/organize/create-folders?dest=${encodeURIComponent(dest)}`,
    { method: "POST" }
  )

export const cleanupEmpty = (directory: string) =>
  request<{ removed: string[] }>(
    `/organize/cleanup-empty?directory=${encodeURIComponent(directory)}`,
    { method: "POST" }
  )

// --- Settings ---
export const getSettingsConfig = () =>
  request<{
    styles_dir: string
    new_releases_dir: string
    master_collection: string
    target_folder_count: number
  }>("/settings/config")

export const getSettingsFolderMapping = () =>
  request<Record<string, string[]>>("/settings/folder-mapping")

export const updateFolderMapping = (mapping: Record<string, string[]>) =>
  request<{ status: string; folders: number }>("/settings/folder-mapping", {
    method: "PUT",
    body: JSON.stringify({ mapping }),
  })

export const getSettingsLabelMapping = () =>
  request<Record<string, string>>("/settings/label-mapping")

export const updateLabelMapping = (mapping: Record<string, string>) =>
  request<{ status: string; labels: number }>("/settings/label-mapping", {
    method: "PUT",
    body: JSON.stringify({ mapping }),
  })

// --- Filesystem browsing ---
export interface BrowseResult {
  current: string
  parent: string
  directories: { name: string; path: string }[]
}

export const browseDirectory = (path = "") =>
  request<BrowseResult>(`/settings/browse?path=${encodeURIComponent(path)}`)
