import { Info, Plus, LogOut, User } from "lucide-react"
import { Button } from "../ui/button"
import { useAuthStore } from "../../store/authStore"
import { useConversationStore } from "../../store/conversationStore"
import { useNavigate } from "react-router-dom"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu"
import { BRANDING } from "../../config/branding"

export function Header() {
  const { user, isAuthenticated, logout } = useAuthStore()
  const { requestConversationSwitch, clearError } = useConversationStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleNewResearch = () => {
    requestConversationSwitch(null)  // null = new chat
    clearError()
  }

  return (
    <header className="flex h-14 items-center gap-4 border-b bg-background/95 backdrop-blur pl-6 pr-4 justify-between">
      <span className="font-semibold text-lg hidden md:block">{BRANDING.name}</span>

      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/about")}
          aria-label={`About ${BRANDING.name}`}
        >
          <Info className="h-5 w-5 text-muted-foreground" />
        </Button>
        <Button
          onClick={handleNewResearch}
          className="h-9 gap-2 rounded-full bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800"
          aria-label="Start new research"
        >
          <Plus className="h-4 w-4" />
          New Research
        </Button>
        
        {isAuthenticated && user && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="rounded-full">
                <User className="h-5 w-5 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <div className="flex flex-col space-y-1">
                  <p className="text-sm font-medium">{user.name}</p>
                  <p className="text-xs text-muted-foreground">{user.email}</p>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                <span>Logout</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  )
}

