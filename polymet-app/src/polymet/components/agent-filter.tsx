import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SearchIcon, FilterIcon } from "lucide-react";

interface AgentFilterProps {
  onFilterChange: (filters: {
    search: string;
    status: string;
    type: string;
  }) => void;
  agentTypes: string[];
}

export function AgentFilter({ onFilterChange, agentTypes }: AgentFilterProps) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("all");

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newSearch = e.target.value;
    setSearch(newSearch);
    onFilterChange({ search: newSearch, status, type });
  };

  const handleStatusChange = (newStatus: string) => {
    setStatus(newStatus);
    onFilterChange({ search, status: newStatus, type });
  };

  const handleTypeChange = (newType: string) => {
    setType(newType);
    onFilterChange({ search, status, type: newType });
  };

  const handleReset = () => {
    setSearch("");
    setStatus("all");
    setType("all");
    onFilterChange({ search: "", status: "all", type: "all" });
  };

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
      <div className="relative w-full md:w-1/3">
        <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search agents..."
          value={search}
          onChange={handleSearchChange}
          className="pl-10"
        />
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2">
          <FilterIcon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm">Filter by:</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={status} onValueChange={handleStatusChange}>
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="paused">Paused</SelectItem>
            </SelectContent>
          </Select>
          <Select value={type} onValueChange={handleTypeChange}>
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              {agentTypes.map((agentType) => (
                <SelectItem key={agentType} value={agentType.toLowerCase()}>
                  {agentType}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={handleReset}>
            Reset
          </Button>
        </div>
      </div>
    </div>
  );
}
