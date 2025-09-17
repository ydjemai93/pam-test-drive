import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { format } from "date-fns";
import { CalendarIcon, FilterIcon, SearchIcon, XIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface CallHistoryFilterProps {
  onFilterChange: (filters: {
    search: string;
    status: string;
    agent: string;
    startDate: Date | undefined;
    endDate: Date | undefined;
  }) => void;
  agentOptions: { id: number; name: string }[];
}

export function CallHistoryFilter({
  onFilterChange,
  agentOptions,
}: CallHistoryFilterProps) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [agent, setAgent] = useState("");
  const [startDate, setStartDate] = useState<Date | undefined>(undefined);
  const [endDate, setEndDate] = useState<Date | undefined>(undefined);
  const [activeFilters, setActiveFilters] = useState(0);

  const handleFilterChange = () => {
    // Count active filters
    let count = 0;
    if (search) count++;
    if (status) count++;
    if (agent) count++;
    if (startDate) count++;
    if (endDate) count++;
    setActiveFilters(count);

    onFilterChange({
      search,
      status,
      agent,
      startDate,
      endDate,
    });
  };

  const resetFilters = () => {
    setSearch("");
    setStatus("");
    setAgent("");
    setStartDate(undefined);
    setEndDate(undefined);
    setActiveFilters(0);
    onFilterChange({
      search: "",
      status: "",
      agent: "",
      startDate: undefined,
      endDate: undefined,
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Search calls, customers, phone numbers..."
            className="pl-8 w-full"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              handleFilterChange();
            }}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value);
              handleFilterChange();
            }}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="missed">Missed</SelectItem>
              <SelectItem value="voicemail">Voicemail</SelectItem>
              <SelectItem value="ongoing">Ongoing</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={agent}
            onValueChange={(value) => {
              setAgent(value);
              handleFilterChange();
            }}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Agent" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Agents</SelectItem>
              {agentOptions.map((agent) => (
                <SelectItem key={agent.id} value={agent.id.toString()}>
                  {agent.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={`w-[130px] justify-start text-left font-normal ${
                    startDate ? "" : "text-muted-foreground"
                  }`}
                >
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {startDate ? format(startDate, "MMM dd, yyyy") : "Start Date"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={startDate}
                  onSelect={(date) => {
                    setStartDate(date);
                    handleFilterChange();
                  }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>

            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={`w-[130px] justify-start text-left font-normal ${
                    endDate ? "" : "text-muted-foreground"
                  }`}
                >
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {endDate ? format(endDate, "MMM dd, yyyy") : "End Date"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={endDate}
                  onSelect={(date) => {
                    setEndDate(date);
                    handleFilterChange();
                  }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FilterIcon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {activeFilters > 0 ? (
              <>
                <Badge variant="secondary" className="rounded-sm mr-1">
                  {activeFilters}
                </Badge>
                filters applied
              </>
            ) : (
              "No filters applied"
            )}
          </span>
        </div>
        {activeFilters > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={resetFilters}
            className="h-8 gap-1 text-muted-foreground"
          >
            <XIcon className="h-4 w-4" />
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}

export default CallHistoryFilter;
