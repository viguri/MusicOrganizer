import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import Layout from "@/components/Layout"
import Dashboard from "@/pages/Dashboard"
import ScanClassify from "@/pages/ScanClassify"
import Organize from "@/pages/Organize"
import NameCleaner from "@/pages/NameCleaner"
import Duplicates from "@/pages/Duplicates"
import Settings from "@/pages/Settings"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/scan" element={<ScanClassify />} />
            <Route path="/organize" element={<Organize />} />
            <Route path="/clean-names" element={<NameCleaner />} />
            <Route path="/duplicates" element={<Duplicates />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
