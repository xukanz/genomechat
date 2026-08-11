import { Sidebar } from "./Sidebar"
import { Header } from "./Header"
import { Outlet } from "react-router-dom"

export function MainLayout() {
  return (
    <div className="flex h-screen w-full bg-background overflow-hidden relative">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden h-full w-full">
        <Header />
        <main className="flex-1 overflow-y-auto relative bg-[#F8FAFC]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

