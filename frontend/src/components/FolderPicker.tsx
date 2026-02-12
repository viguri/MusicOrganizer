import { useCallback, useState } from "react"
import { Folder, FolderOpen, ChevronUp, HardDrive } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { browseDirectory } from "@/lib/api"

interface FolderPickerProps {
  value: string
  onChange: (path: string) => void
  placeholder?: string
  label?: string
  className?: string
}

export default function FolderPicker({
  value,
  onChange,
  placeholder = "Select a folder...",
  label,
  className,
}: FolderPickerProps) {
  const [open, setOpen] = useState(false)
  const [currentPath, setCurrentPath] = useState("")
  const [parentPath, setParentPath] = useState("")
  const [dirs, setDirs] = useState<{ name: string; path: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const browse = useCallback(async (path: string) => {
    setLoading(true)
    setError("")
    try {
      const result = await browseDirectory(path)
      setCurrentPath(result.current)
      setParentPath(result.parent)
      setDirs(result.directories)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to browse")
    }
    setLoading(false)
  }, [])

  const handleOpen = () => {
    setOpen(true)
    browse(value || "")
  }

  const handleSelect = () => {
    if (currentPath) {
      onChange(currentPath)
    }
    setOpen(false)
  }

  return (
    <div className={className}>
      {label && (
        <label className="text-xs text-muted-foreground mb-1 block">{label}</label>
      )}
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 font-mono text-sm"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0 px-3"
          onClick={handleOpen}
          title="Browse folders"
        >
          <FolderOpen className="h-4 w-4" />
        </Button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Folder className="h-5 w-5" /> Select Folder
            </DialogTitle>
          </DialogHeader>

          <div className="flex items-center gap-2 px-1 py-2 bg-muted/50 rounded text-sm font-mono truncate min-h-[36px]">
            {currentPath ? (
              <>
                <HardDrive className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{currentPath}</span>
              </>
            ) : (
              <span className="text-muted-foreground">Select a drive...</span>
            )}
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="flex-1 overflow-auto border rounded-md min-h-[250px] max-h-[400px]">
            {parentPath !== "" && (
              <button
                type="button"
                className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50 border-b text-muted-foreground"
                onClick={() => browse(parentPath)}
                disabled={loading}
              >
                <ChevronUp className="h-4 w-4" />
                ..
              </button>
            )}
            {currentPath && !parentPath && (
              <button
                type="button"
                className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50 border-b text-muted-foreground"
                onClick={() => browse("")}
                disabled={loading}
              >
                <ChevronUp className="h-4 w-4" />
                Back to drives
              </button>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                Loading...
              </div>
            ) : dirs.length === 0 ? (
              <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
                No subdirectories
              </div>
            ) : (
              dirs.map((dir) => (
                <button
                  key={dir.path}
                  type="button"
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted/50 border-b last:border-b-0 text-left"
                  onDoubleClick={() => browse(dir.path)}
                  onClick={() => {
                    setCurrentPath(dir.path)
                  }}
                >
                  <Folder className="h-4 w-4 shrink-0 text-amber-500" />
                  <span className="truncate">{dir.name}</span>
                </button>
              ))
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            Click to select, double-click to enter a folder
          </p>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSelect} disabled={!currentPath}>
              Select this folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
