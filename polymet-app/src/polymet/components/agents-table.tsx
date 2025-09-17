import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PhoneIcon, TrashIcon } from "lucide-react";
import { Agent } from "@/polymet/data/agents-data";
import { Link, useNavigate } from "react-router-dom";
import { DeleteConfirmationDialog } from "@/polymet/components/delete-confirmation-dialog";
import { toast } from "@/polymet/components/sonner";

interface AgentsTableProps {
  agents: Agent[];
  onDeleteAgent?: (agentId: number) => void;
}

export function AgentsTable({ agents, onDeleteAgent }: AgentsTableProps) {
  const navigate = useNavigate();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<number | null>(null);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active":
        return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
      case "draft":
        return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400";
      case "paused":
        return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400";
      default:
        return "";
    }
  };

  const handleRowClick = (agentId: number) => {
    navigate(`/agents/${agentId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, agentId: number) => {
    e.stopPropagation(); // Prevent row click from triggering
    setAgentToDelete(agentId);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = () => {
    if (agentToDelete !== null && onDeleteAgent) {
      onDeleteAgent(agentToDelete);
    }
    setDeleteDialogOpen(false);
    setAgentToDelete(null);
  };

  return (
    <div className="rounded-md border font-thin">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[300px]">Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Calls</TableHead>
            <TableHead>Last Modified</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="w-[80px]">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {agents.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="h-24 text-center">
                No agents found.
              </TableCell>
            </TableRow>
          ) : (
            agents.map((agent) => (
              <TableRow
                key={agent.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => handleRowClick(agent.id)}
              >
                <TableCell className="font-medium">
                  <div className="flex items-center space-x-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <PhoneIcon className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <div className="font-medium">{agent.name}</div>
                      <div className="text-sm text-muted-foreground truncate max-w-[200px]">
                        {agent.description}
                      </div>
                    </div>
                  </div>
                </TableCell>
                <TableCell>{agent.type}</TableCell>
                <TableCell>
                  <Badge
                    variant="secondary"
                    className={`capitalize ${getStatusColor(agent.status)}`}
                  >
                    {agent.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">{agent.calls}</TableCell>
                <TableCell>{agent.lastModified}</TableCell>
                <TableCell>{agent.createdAt}</TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    onClick={(e) => handleDeleteClick(e, agent.id)}
                    title="Delete agent"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <DeleteConfirmationDialog
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={handleConfirmDelete}
        title="Delete Agent"
        description="Are you sure you want to delete this agent? This action cannot be undone and all associated data will be permanently removed."
      />
    </div>
  );
}
