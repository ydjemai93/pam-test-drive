import React, { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Download, FileDown, Phone } from "lucide-react";
import CallHistoryFilter from "@/polymet/components/call-history-filter";
import CallList from "@/polymet/components/call-list";
import { CALLS_DATA, Call } from "@/polymet/data/calls-data";
import { Pagination } from "@/components/ui/pagination";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function CallHistoryPage() {
  const [filters, setFilters] = useState({
    search: "",
    status: "",
    agent: "",
    startDate: undefined,
    endDate: undefined,
  });

  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);

  // Extract unique agent options for the filter dropdown
  const agentOptions = useMemo(() => {
    const agents = new Set(
      CALLS_DATA.map((call) => ({
        id: call.agentId,
        name: call.agentName,
      }))
    );

    // Convert to array and remove duplicates
    return Array.from(agents).filter(
      (agent, index, self) => index === self.findIndex((a) => a.id === agent.id)
    );
  }, []);

  // Filter calls based on search, status, agent, and date range
  const filteredCalls = useMemo(() => {
    return CALLS_DATA.filter((call: Call) => {
      const matchesSearch =
        filters.search === "" ||
        call.customerName
          .toLowerCase()
          .includes(filters.search.toLowerCase()) ||
        call.phoneNumber.toLowerCase().includes(filters.search.toLowerCase()) ||
        call.agentName.toLowerCase().includes(filters.search.toLowerCase());

      const matchesStatus =
        filters.status === "" || call.status === filters.status;

      const matchesAgent =
        filters.agent === "" || call.agentId.toString() === filters.agent;

      const matchesDateRange =
        (!filters.startDate || new Date(call.timestamp) >= filters.startDate) &&
        (!filters.endDate || new Date(call.timestamp) <= filters.endDate);

      return matchesSearch && matchesStatus && matchesAgent && matchesDateRange;
    });
  }, [filters]);

  // Calculate pagination
  const totalPages = Math.ceil(filteredCalls.length / itemsPerPage);
  const paginatedCalls = filteredCalls.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  const handleFilterChange = (newFilters: {
    search: string;
    status: string;
    agent: string;
    startDate: Date | undefined;
    endDate: Date | undefined;
  }) => {
    setFilters(newFilters);
    setCurrentPage(1); // Reset to first page when filters change
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handleItemsPerPageChange = (value: string) => {
    setItemsPerPage(Number(value));
    setCurrentPage(1); // Reset to first page when items per page changes
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Call History</h1>
          <p className="text-muted-foreground">
            View and manage all your call recordings and transcripts
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button variant="outline">
            <Download className="h-4 w-4 mr-2" />
            Export Calls
          </Button>
          <Button>
            <FileDown className="h-4 w-4 mr-2" />
            Download Report
          </Button>
        </div>
      </div>

      <div className="bg-card rounded-lg border shadow-sm p-6">
        <div className="mb-4">
          <h2 className="text-xl font-semibold mb-2">Call Management</h2>
          <p className="text-muted-foreground">
            Filter, search, and manage your call recordings from one place
          </p>
        </div>

        <CallHistoryFilter
          onFilterChange={handleFilterChange}
          agentOptions={agentOptions}
        />

        <div className="mt-6">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-muted-foreground">
              Showing {paginatedCalls.length} of {filteredCalls.length} calls
            </p>
            <div className="flex items-center space-x-2">
              <span className="text-sm text-muted-foreground">Show</span>
              <Select
                value={itemsPerPage.toString()}
                onValueChange={handleItemsPerPageChange}
              >
                <SelectTrigger className="w-[80px]">
                  <SelectValue placeholder="10" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">5</SelectItem>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="20">20</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                </SelectContent>
              </Select>
              <span className="text-sm text-muted-foreground">per page</span>
            </div>
          </div>

          <CallList calls={paginatedCalls} isLoading={false} />

          {filteredCalls.length > 0 && (
            <div className="flex items-center justify-between mt-4">
              <div className="text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </div>
              <div className="flex items-center space-x-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handlePageChange(Math.max(currentPage - 1, 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </Button>
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  // Show pages around current page
                  let pageToShow = i + 1;
                  if (totalPages > 5 && currentPage > 3) {
                    pageToShow = currentPage - 2 + i;
                  }
                  if (pageToShow > totalPages) return null;

                  return (
                    <Button
                      key={pageToShow}
                      variant={
                        currentPage === pageToShow ? "default" : "outline"
                      }
                      size="sm"
                      className="w-8 h-8"
                      onClick={() => handlePageChange(pageToShow)}
                    >
                      {pageToShow}
                    </Button>
                  );
                })}
                {totalPages > 5 && currentPage < totalPages - 2 && (
                  <>
                    <span className="text-muted-foreground">...</span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-8 h-8"
                      onClick={() => handlePageChange(totalPages)}
                    >
                      {totalPages}
                    </Button>
                  </>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    handlePageChange(Math.min(currentPage + 1, totalPages))
                  }
                  disabled={currentPage === totalPages}
                >
                  Next
                </Button>
              </div>
            </div>
          )}

          {filteredCalls.length === 0 && (
            <div className="text-center py-8">
              <Phone className="h-12 w-12 mx-auto text-muted-foreground opacity-20" />
              <h3 className="mt-4 text-lg font-medium">No calls found</h3>
              <p className="text-muted-foreground">
                Try adjusting your filters or search criteria
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
