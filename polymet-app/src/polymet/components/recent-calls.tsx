import React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
import {
  DownloadIcon,
  PlayIcon,
  ArrowRightIcon,
  PhoneIcon,
  PhoneOutgoingIcon,
  PhoneIncomingIcon,
  CheckCircleIcon,
  XIcon,
} from "lucide-react";

export function RecentCalls() {
  const calls = [
    {
      id: 1,
      caller: "+1 (555) 123-4567",
      agent: "Customer Support Agent",
      duration: "4:32",
      status: "completed",
      outcome: "Issue Resolved",
      date: "2023-06-12 14:23",
      type: "incoming",
    },
    {
      id: 2,
      caller: "+1 (555) 987-6543",
      agent: "Sales Representative",
      duration: "8:17",
      status: "completed",
      outcome: "Demo Scheduled",
      date: "2023-06-12 11:05",
      type: "outgoing",
    },
    {
      id: 3,
      caller: "+1 (555) 456-7890",
      agent: "Appointment Scheduler",
      duration: "2:45",
      status: "completed",
      outcome: "Appointment Confirmed",
      date: "2023-06-11 16:42",
      type: "incoming",
    },
    {
      id: 4,
      caller: "+1 (555) 234-5678",
      agent: "Customer Support Agent",
      duration: "5:11",
      status: "missed",
      outcome: "N/A",
      date: "2023-06-11 09:18",
      type: "incoming",
    },
    {
      id: 5,
      caller: "+1 (555) 876-5432",
      agent: "Sales Representative",
      duration: "6:03",
      status: "completed",
      outcome: "Not Interested",
      date: "2023-06-10 15:37",
      type: "outgoing",
    },
  ];

  return (
    <Card id="c60mjv">
      <CardHeader
        className="flex flex-row items-center justify-between space-y-0 pb-2"
        id="ms53xu"
      >
        <div id="q9sxyw">
          <CardTitle id="ctjaaj">Recent Calls</CardTitle>
          <CardDescription id="ulujna">
            Your AI agents' latest interactions
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" className="gap-1" id="yslzo2">
          <DownloadIcon className="h-3.5 w-3.5" id="8qa57h" />
          Export
        </Button>
      </CardHeader>
      <CardContent id="qu7ktw">
        <Table id="dk6vs0">
          <TableHeader id="9wuwck">
            <TableRow id="xxvotp">
              <TableHead id="2cm30g">Caller</TableHead>
              <TableHead id="07u4tw">Agent</TableHead>
              <TableHead id="axo33y">Duration</TableHead>
              <TableHead id="mzsksp">Status</TableHead>
              <TableHead id="mvjbna">Outcome</TableHead>
              <TableHead id="k52hkc">Date & Time</TableHead>
              <TableHead className="text-right" id="mc7bgt">
                Actions
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody id="cdn29h">
            {calls.map((call, index) => (
              <TableRow key={call.id} id={`vyw2pw_${index}`}>
                <TableCell id={`6slog7_${index}`}>
                  <div
                    className="flex items-center gap-2"
                    id={`yak27o_${index}`}
                  >
                    {call.type === "incoming" ? (
                      <PhoneIncomingIcon
                        className="h-4 w-4 text-green-500"
                        id={`rw7bvl_${index}`}
                      />
                    ) : (
                      <PhoneOutgoingIcon
                        className="h-4 w-4 text-blue-500"
                        id={`jmtjj0_${index}`}
                      />
                    )}

                    <span id={`d2ja7i_${index}`}>{call.caller}</span>
                  </div>
                </TableCell>
                <TableCell id={`fj0qoi_${index}`}>
                  <div
                    className="flex items-center gap-2"
                    id={`bqlvm3_${index}`}
                  >
                    <Avatar className="h-6 w-6" id={`vrsdvp_${index}`}>
                      <AvatarImage
                        src={`https://i.pravatar.cc/150?img=${call.id}`}
                        alt={call.agent}
                        id={`4nqdal_${index}`}
                      />

                      <AvatarFallback id={`cvj6oh_${index}`}>AI</AvatarFallback>
                    </Avatar>
                    <span className="whitespace-nowrap" id={`lauwxa_${index}`}>
                      {call.agent}
                    </span>
                  </div>
                </TableCell>
                <TableCell id={`jzr0bx_${index}`}>{call.duration}</TableCell>
                <TableCell id={`buqhty_${index}`}>
                  <Badge
                    variant={
                      call.status === "completed" ? "default" : "destructive"
                    }
                    className="capitalize"
                    id={`kedhwy_${index}`}
                  >
                    {call.status}
                  </Badge>
                </TableCell>
                <TableCell id={`e8ncvm_${index}`}>
                  <div
                    className="flex items-center gap-1"
                    id={`7jijms_${index}`}
                  >
                    {call.outcome !== "N/A" &&
                    call.outcome !== "Not Interested" ? (
                      <CheckCircleIcon
                        className="h-4 w-4 text-green-500"
                        id={`2vl2gt_${index}`}
                      />
                    ) : call.outcome === "Not Interested" ? (
                      <XIcon
                        className="h-4 w-4 text-red-500"
                        id={`3c2rd1_${index}`}
                      />
                    ) : (
                      <XIcon
                        className="h-4 w-4 text-muted-foreground"
                        id={`uvhh9b_${index}`}
                      />
                    )}

                    <span id={`glw8i8_${index}`}>{call.outcome}</span>
                  </div>
                </TableCell>
                <TableCell
                  className="text-muted-foreground text-sm"
                  id={`ym4sdo_${index}`}
                >
                  {call.date}
                </TableCell>
                <TableCell className="text-right" id={`80khjy_${index}`}>
                  <Button variant="ghost" size="icon" id={`mvi2md_${index}`}>
                    <PlayIcon className="h-4 w-4" id={`dj519g_${index}`} />
                    <span className="sr-only" id={`w7vbg1_${index}`}>
                      Play recording
                    </span>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="mt-4 flex justify-center" id="p38e4h">
          <Button variant="outline" className="gap-1" id="9vbut3">
            View All Calls
            <ArrowRightIcon className="h-4 w-4" id="igecnw" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
