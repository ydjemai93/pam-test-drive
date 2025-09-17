import React, { useState } from "react";
import { Check, ChevronsUpDownIcon, ZapIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { Agent } from "@/polymet/data/agents-data";

interface AgentSelectorProps {
  agents: Agent[];
  selectedAgent: Agent | null;
  onSelect: (agent: Agent) => void;
  className?: string;
}

export function AgentSelector({
  agents,
  selectedAgent,
  onSelect,
  className,
}: AgentSelectorProps) {
  const [open, setOpen] = useState(false);

  // Filter to only show active agents
  const activeAgents = agents.filter((agent) => agent.status === "active");

  return (
    <div className={cn("space-y-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className={cn(
              "w-full justify-between",
              !selectedAgent && "text-muted-foreground"
            )}
          >
            {selectedAgent ? (
              <div className="flex items-center gap-2">
                <ZapIcon className="h-4 w-4 text-[#2E8B57]" />
                <span>{selectedAgent.name}</span>
              </div>
            ) : (
              "Select an agent"
            )}
            <ChevronsUpDownIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[300px] p-0">
          <Command>
            <CommandInput placeholder="Search agents..." />
            <CommandEmpty>No agents found.</CommandEmpty>
            <CommandGroup>
              {activeAgents.map((agent) => (
                <CommandItem
                  key={agent.id}
                  value={agent.name}
                  onSelect={() => {
                    onSelect(agent);
                    setOpen(false);
                  }}
                >
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-2">
                      <ZapIcon className="h-4 w-4 text-[#2E8B57]" />
                      <span>{agent.name}</span>
                    </div>
                    <Badge variant="outline" className="ml-2">
                      {agent.type}
                    </Badge>
                  </div>
                  <Check
                    className={cn(
                      "ml-auto h-4 w-4",
                      selectedAgent?.id === agent.id
                        ? "opacity-100"
                        : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </Command>
        </PopoverContent>
      </Popover>
      {selectedAgent && (
        <p className="text-sm text-muted-foreground">
          {selectedAgent.description}
        </p>
      )}
    </div>
  );
}

export default AgentSelector;
