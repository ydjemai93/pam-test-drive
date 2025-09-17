import React from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PlusIcon, ZapIcon, HeadphonesIcon, CalendarIcon } from "lucide-react";

export function CreateAgentCard() {
  return (
    <Card
      className="bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20 p-4 space-y-4"
      id="gndcff"
    >
      <Button
        variant="outline"
        className="w-full justify-start gap-2 bg-background/80"
        id="pmatwr"
      >
        <ZapIcon className="h-4 w-4 text-primary" id="i5f7kh" />

        <div className="flex flex-col items-start" id="n6hq47">
          <span id="tpb98k">Customer Support</span>
          <span className="text-xs text-muted-foreground" id="2bbta8">
            Handle inquiries & issues
          </span>
        </div>
      </Button>
      <Button
        variant="outline"
        className="w-full justify-start gap-2 bg-background/80"
        id="y4ffgu"
      >
        <HeadphonesIcon className="h-4 w-4 text-primary" id="b88302" />

        <div className="flex flex-col items-start" id="qfsjkp">
          <span id="x9vspb">Sales Agent</span>
          <span className="text-xs text-muted-foreground" id="y192ig">
            Qualify leads & book demos
          </span>
        </div>
      </Button>
      <Button
        variant="outline"
        className="w-full justify-start gap-2 bg-background/80"
        id="dge7pd"
      >
        <CalendarIcon className="h-4 w-4 text-primary" id="o84ley" />

        <div className="flex flex-col items-start" id="d44cg5">
          <span id="ni4ra6">Appointment Scheduler</span>
          <span className="text-xs text-muted-foreground" id="8ce78u">
            Book & confirm appointments
          </span>
        </div>
      </Button>
      <Button variant="default" className="w-full gap-2" id="9esjsp">
        <PlusIcon className="h-4 w-4" id="eis66u" />
        Custom Agent
      </Button>
    </Card>
  );
}
