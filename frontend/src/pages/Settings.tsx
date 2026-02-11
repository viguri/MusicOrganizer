import { useEffect, useState } from "react"
import { Settings as SettingsIcon, Save } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { getSettingsConfig, getSettingsFolderMapping, getSettingsLabelMapping, updateFolderMapping, updateLabelMapping } from "@/lib/api"


export default function Settings() {
  const [tab, setTab] = useState("general")
  const [config, setConfig] = useState({
    styles_dir: "",
    new_releases_dir: "",
    master_collection: "",
    target_folder_count: 50,
  })
  const [folderMapping, setFolderMapping] = useState<Record<string, string[]>>({})
  const [labelMapping, setLabelMapping] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState("")

  useEffect(() => {
    getSettingsConfig()
      .then((c) => setConfig(c))
      .catch(() => {})
    getSettingsFolderMapping()
      .then((m) => setFolderMapping(m))
      .catch(() => {})
    getSettingsLabelMapping()
      .then((m) => setLabelMapping(m))
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Settings</h2>
        <p className="text-muted-foreground">Configure paths, mappings, and options</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="general">
            <SettingsIcon className="h-4 w-4 mr-1" /> General
          </TabsTrigger>
          <TabsTrigger value="folders">Folder Mapping</TabsTrigger>
          <TabsTrigger value="labels">Label Mapping</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Paths & Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Master Collection</label>
                <Input
                  value={config.master_collection}
                  onChange={(e) => setConfig({ ...config, master_collection: e.target.value })}
                  className="font-mono text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Styles Directory</label>
                <Input
                  value={config.styles_dir}
                  onChange={(e) => setConfig({ ...config, styles_dir: e.target.value })}
                  className="font-mono text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">New Releases Directory</label>
                <Input
                  value={config.new_releases_dir}
                  onChange={(e) => setConfig({ ...config, new_releases_dir: e.target.value })}
                  className="font-mono text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Target Folder Count</label>
                <Input
                  type="number"
                  value={config.target_folder_count}
                  onChange={(e) => setConfig({ ...config, target_folder_count: Number(e.target.value) })}
                  className="w-24"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Path configuration is set via environment variables or backend/config.py.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="folders">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Folder Mapping ({Object.keys(folderMapping).length} folders)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-4">
                <Button
                  size="sm"
                  disabled={saving || Object.keys(folderMapping).length === 0}
                  onClick={async () => {
                    setSaving(true)
                    try {
                      await updateFolderMapping(folderMapping)
                      setSaveMsg("Folder mapping saved")
                    } catch { setSaveMsg("Save failed") }
                    setSaving(false)
                    setTimeout(() => setSaveMsg(""), 3000)
                  }}
                >
                  <Save className="h-4 w-4" /> Save Folder Mapping
                </Button>
                {saveMsg && <Badge variant="secondary">{saveMsg}</Badge>}
              </div>
              {Object.keys(folderMapping).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No folder mapping yet. Run "Analyze Genres" in the Scan page first.
                </p>
              ) : (
                <div className="border rounded-md overflow-auto max-h-[500px]">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        <th className="text-left p-2 font-medium w-48">Folder</th>
                        <th className="text-left p-2 font-medium">Genres</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(folderMapping)
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([folder, genres]) => (
                          <tr key={folder} className="border-t hover:bg-muted/30">
                            <td className="p-2 font-mono text-xs font-medium">{folder}</td>
                            <td className="p-2">
                              <div className="flex flex-wrap gap-1">
                                {genres.map((g) => (
                                  <span key={g} className="px-1.5 py-0.5 bg-muted rounded text-xs">
                                    {g}
                                  </span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="labels">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Label Mapping ({Object.keys(labelMapping).length} labels)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-4">
                <Button
                  size="sm"
                  disabled={saving || Object.keys(labelMapping).length === 0}
                  onClick={async () => {
                    setSaving(true)
                    try {
                      await updateLabelMapping(labelMapping)
                      setSaveMsg("Label mapping saved")
                    } catch { setSaveMsg("Save failed") }
                    setSaving(false)
                    setTimeout(() => setSaveMsg(""), 3000)
                  }}
                >
                  <Save className="h-4 w-4" /> Save Label Mapping
                </Button>
                {saveMsg && <Badge variant="secondary">{saveMsg}</Badge>}
              </div>
              {Object.keys(labelMapping).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No label mapping yet. Run "Analyze Genres" in the Scan page first.
                </p>
              ) : (
                <div className="border rounded-md overflow-auto max-h-[500px]">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 sticky top-0">
                      <tr>
                        <th className="text-left p-2 font-medium">Label</th>
                        <th className="text-left p-2 font-medium">Genre</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(labelMapping)
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([label, genre]) => (
                          <tr key={label} className="border-t hover:bg-muted/30">
                            <td className="p-2 text-xs">{label}</td>
                            <td className="p-2 text-xs font-medium">{genre}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
