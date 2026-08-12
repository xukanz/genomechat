import { motion } from "framer-motion"
import { Search, FileText, Microscope, Dna } from "lucide-react"
import { Card, CardHeader, CardTitle } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { useNavigate } from "react-router-dom"
import { MessageInput } from "../components/chat/MessageInput"

export function Dashboard() {
  const navigate = useNavigate()

  const quickActions = [
    {
      title: "Analyze Patient Data",
      description: "Upload VCF/CSV files for variant analysis",
      icon: Dna,
      color: "text-blue-600",
      bgColor: "bg-blue-100/50",
    },
    {
      title: "Clinical Trial Search",
      description: "Find relevant trials for specific indications",
      icon: Search,
      color: "text-green-600",
      bgColor: "bg-green-100/50",
    },
    {
      title: "Generate Report",
      description: "Create summary reports from analysis results",
      icon: FileText,
      color: "text-purple-600",
      bgColor: "bg-purple-100/50",
    },
    {
      title: "Literature Review",
      description: "Deep search across PubMed and medical databases",
      icon: Microscope,
      color: "text-orange-600",
      bgColor: "bg-orange-100/50",
    },
  ]

  const handleSendMessage = (message: string) => {
    navigate('/chat', { state: { initialMessage: message } })
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-full p-4 lg:p-8 space-y-8 bg-[#F8FAFC]">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center space-y-6 max-w-3xl mx-auto w-full pt-10"
      >
        <div className="flex flex-col items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-blue-100 flex items-center justify-center mb-2">
                <div className="h-8 w-8 rounded-full bg-primary" />
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-foreground">
              Hi, there <span className="text-4xl">👋</span>
            </h1>
            <p className="text-xl text-muted-foreground">
              Tell us what you need, and we'll handle the rest.
            </p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2, duration: 0.5 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 max-w-5xl w-full"
      >
        {/* Large Dark Card - Data Assistant */}
        <motion.div 
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            className="col-span-1 md:col-span-2 row-span-2"
        >
            <Card 
                className="cursor-pointer h-full border-none bg-[#1E293B] text-white hover:shadow-xl transition-all duration-300 relative overflow-hidden group"
                onClick={() => navigate('/chat')}
            >
              <CardHeader className="space-y-4 p-8 relative z-10">
                <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 font-bold text-xs">
                        SL
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">Sam Lee</span>
                        <span className="text-[10px] bg-blue-500 text-white px-2 py-0.5 rounded-full font-medium">Data Assistant</span>
                    </div>
                </div>
                
                <div className="space-y-2 mt-4">
                    <p className="text-sm text-gray-400 leading-relaxed max-w-md">
                        Designed to help manage sales processes and maximize customer engagement.
                    </p>
                </div>
              </CardHeader>
              
              {/* Abstract decorative shape */}
              <div className="absolute -bottom-20 -right-20 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl group-hover:bg-blue-500/20 transition-colors duration-500" />
            </Card>
        </motion.div>

        {/* Smaller Cards */}
        {quickActions.slice(1).map((action) => (
          <motion.div
            key={action.title}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            className="col-span-1"
          >
            <Card 
                className="cursor-pointer hover:shadow-md transition-all duration-200 h-full border-border/50 bg-white"
                onClick={() => navigate('/chat')}
            >
              <CardHeader className="space-y-3 p-5">
                <div className="flex items-start justify-between">
                    <action.icon className="h-5 w-5 text-muted-foreground" />
                    <Button variant="ghost" size="icon" className="h-6 w-6 -mt-1 -mr-2 text-muted-foreground/50">
                        <span className="sr-only">Menu</span>
                        <div className="flex gap-0.5">
                            <div className="w-1 h-1 rounded-full bg-current" />
                            <div className="w-1 h-1 rounded-full bg-current" />
                            <div className="w-1 h-1 rounded-full bg-current" />
                        </div>
                    </Button>
                </div>
                <CardTitle className="text-sm font-medium leading-tight">{action.description}</CardTitle>
                <div className="pt-2">
                    <span className="text-xs text-blue-600 font-medium hover:underline">View All</span>
                </div>
              </CardHeader>
            </Card>
          </motion.div>
        ))}
        
        {/* Suggested Prompt Card */}
         <motion.div
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            className="col-span-1"
          >
            <Card 
                className="cursor-pointer hover:shadow-md transition-all duration-200 h-full border-border/50 bg-white flex flex-col justify-between"
                onClick={() => navigate('/chat')}
            >
              <CardHeader className="space-y-3 p-5">
                <div className="flex items-start justify-between">
                     <div className="flex gap-0.5 mt-1">
                        <div className="w-1 h-1 rounded-full bg-muted-foreground" />
                        <div className="w-1 h-1 rounded-full bg-muted-foreground" />
                        <div className="w-1 h-1 rounded-full bg-muted-foreground" />
                    </div>
                </div>
                <p className="text-sm font-medium leading-tight text-foreground/80">
                    What are the key benefits of Product 1 that I should highlight to potential clients?
                </p>
              </CardHeader>
              <div className="p-5 pt-0">
                <p className="text-xs text-muted-foreground">Suggested prompt</p>
              </div>
            </Card>
          </motion.div>
      </motion.div>

      {/* Bottom Action Bar */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.5 }}
        className="max-w-4xl w-full flex items-center justify-center gap-3 pt-4 pb-20"
      >
        <Button variant="outline" className="h-12 px-6 rounded-full border-border/50 bg-white hover:bg-slate-50 gap-2 shadow-sm text-sm font-medium text-foreground/80">
            <span className="p-1 rounded bg-red-100 text-red-500"><FileText className="h-3 w-3" /></span>
            Connect Calendar
        </Button>
        <Button variant="outline" className="h-12 px-6 rounded-full border-border/50 bg-white hover:bg-slate-50 gap-2 shadow-sm text-sm font-medium text-foreground/80">
            <span className="p-1 rounded bg-blue-100 text-blue-500"><Search className="h-3 w-3" /></span>
            Demo Task
        </Button>
        <Button variant="outline" className="h-12 px-6 rounded-full border-border/50 bg-white hover:bg-slate-50 gap-2 shadow-sm text-sm font-medium text-foreground/80">
            <span className="p-1 rounded bg-orange-100 text-orange-500"><Microscope className="h-3 w-3" /></span>
            Browse Integrations
        </Button>
        <Button variant="outline" className="h-12 px-6 rounded-full border-border/50 bg-white hover:bg-slate-50 gap-2 shadow-sm text-sm font-medium text-foreground/80">
            <span className="p-1 rounded bg-green-100 text-green-500"><Dna className="h-3 w-3" /></span>
            Shared in Notes
        </Button>
      </motion.div>
      
      {/* Floating Input Area - Fixed at bottom */}
      <div className="fixed bottom-8 left-0 right-0 px-4 flex justify-center z-50 pointer-events-none">
        <div className="w-full max-w-3xl pointer-events-auto shadow-2xl rounded-3xl">
             <MessageInput onSendMessage={handleSendMessage} />
        </div>
      </div>
    </div>
  )
}
