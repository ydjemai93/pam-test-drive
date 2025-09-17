import React from "react";
import { Call } from "@/polymet/data/calls-data";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Clock,
  Download,
  Eye,
  FileDown,
  MoreHorizontal,
  Phone,
  PhoneMissedIcon,
  PlayIcon,
  UserIcon,
  VolumeIcon,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

interface CallListProps {
  calls: Call[];
  isLoading?: boolean;
}

export function CallList({ calls, isLoading = false }: CallListProps) {
  const getStatusIcon = (status: Call["status"]) => {
    switch (status) {
      case "completed":
        return <Phone className="h-4 w-4 text-green-500" />;
      case "missed":
        return <PhoneMissedIcon className="h-4 w-4 text-red-500" />;
      case "voicemail":
        return <VolumeIcon className="h-4 w-4 text-blue-500" />;
      case "ongoing":
        return <Clock className="h-4 w-4 text-yellow-500" />;
      default:
        return <Phone className="h-4 w-4" />;
    }
  };

  const getStatusBadge = (status: Call["status"]) => {
    switch (status) {
      case "completed":
        return (
          <Badge
            variant="outline"
            className="bg-green-50 text-green-700 border-green-200"
          >
            Completed
          </Badge>
        );

      case "missed":
        return (
          <Badge
            variant="outline"
            className="bg-red-50 text-red-700 border-red-200"
          >
            Missed
          </Badge>
        );

      case "voicemail":
        return (
          <Badge
            variant="outline"
            className="bg-blue-50 text-blue-700 border-blue-200"
          >
            Voicemail
          </Badge>
        );

      case "ongoing":
        return (
          <Badge
            variant="outline"
            className="bg-yellow-50 text-yellow-700 border-yellow-200"
          >
            Ongoing
          </Badge>
        );

      default:
        return <Badge variant="outline">Unknown</Badge>;
    }
  };

  const getOutcomeBadge = (outcome?: Call["outcome"]) => {
    if (!outcome) return null;

    switch (outcome) {
      case "conversion":
        return (
          <Badge
            variant="outline"
            className="bg-purple-50 text-purple-700 border-purple-200"
          >
            Conversion
          </Badge>
        );

      case "follow-up":
        return (
          <Badge
            variant="outline"
            className="bg-blue-50 text-blue-700 border-blue-200"
          >
            Follow-up
          </Badge>
        );

      case "no-interest":
        return (
          <Badge
            variant="outline"
            className="bg-gray-50 text-gray-700 border-gray-200"
          >
            No Interest
          </Badge>
        );

      case "information":
        return (
          <Badge
            variant="outline"
            className="bg-teal-50 text-teal-700 border-teal-200"
          >
            Information
          </Badge>
        );

      default:
        return null;
    }
  };

  const formatTime = (timestamp: string) => {
    try {
      return formatDistanceToNow(new Date(timestamp), { addSuffix: true });
    } catch (e) {
      return "Invalid date";
    }
  };

  if (isLoading) {
    return <div>Loading calls...</div>;
  }

  if (calls.length === 0) {
    return (
      <div className="text-center py-8">
        <Phone className="h-12 w-12 mx-auto text-muted-foreground opacity-20" />
        <h3 className="mt-4 text-lg font-medium">No calls found</h3>
        <p className="text-muted-foreground">
          Try adjusting your filters or search criteria
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[250px]">Customer</TableHead>
            <TableHead>Agent</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Outcome</TableHead>
            <TableHead>Time</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {calls.map((call) => (
            <TableRow key={call.id}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <Avatar className="h-8 w-8">
                    <AvatarFallback>
                      <UserIcon className="h-4 w-4" />
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <div className="font-medium">{call.customerName}</div>
                    <div className="text-sm text-muted-foreground">
                      {call.phoneNumber}
                    </div>
                  </div>
                </div>
              </TableCell>
              <TableCell>{call.agentName}</TableCell>
              <TableCell>{call.duration}</TableCell>
              <TableCell>{getStatusBadge(call.status)}</TableCell>
              <TableCell>{getOutcomeBadge(call.outcome)}</TableCell>
              <TableCell>{formatTime(call.timestamp)}</TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                      <span className="sr-only">Open menu</span>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem>
                      <Eye className="mr-2 h-4 w-4" />
                      View Details
                    </DropdownMenuItem>
                    {call.recordingUrl && (
                      <>
                        <DropdownMenuItem>
                          <PlayIcon className="mr-2 h-4 w-4" />
                          Play Recording
                        </DropdownMenuItem>
                        <DropdownMenuItem>
                          <Download className="mr-2 h-4 w-4" />
                          Download Recording
                        </DropdownMenuItem>
                      </>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem>
                      <FileDown className="mr-2 h-4 w-4" />
                      Export Call Data
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default CallList;
