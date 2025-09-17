export interface Agent {
  id: number;
  name: string;
  description: string;
  calls: number;
  avgRating: number;
  status: "active" | "draft" | "paused";
  lastModified: string;
  type: string;
  createdAt: string;
}

export const AGENTS_DATA: Agent[] = [
  {
    id: 1,
    name: "Customer Support Agent",
    description: "Handles general inquiries and support requests",
    calls: 423,
    avgRating: 4.8,
    status: "active",
    lastModified: "2 hours ago",
    type: "Support",
    createdAt: "2023-10-15",
  },
  {
    id: 2,
    name: "Sales Representative",
    description: "Qualifies leads and schedules demos with prospects",
    calls: 287,
    avgRating: 4.6,
    status: "active",
    lastModified: "1 day ago",
    type: "Sales",
    createdAt: "2023-10-20",
  },
  {
    id: 3,
    name: "Appointment Scheduler",
    description: "Books and confirms appointments for service team",
    calls: 156,
    avgRating: 4.9,
    status: "active",
    lastModified: "3 days ago",
    type: "Scheduling",
    createdAt: "2023-11-05",
  },
  {
    id: 4,
    name: "Product Specialist",
    description: "Provides detailed information about products and features",
    calls: 98,
    avgRating: 4.7,
    status: "active",
    lastModified: "5 days ago",
    type: "Support",
    createdAt: "2023-11-10",
  },
  {
    id: 5,
    name: "Feedback Collector",
    description: "Gathers customer feedback and satisfaction ratings",
    calls: 76,
    avgRating: 4.5,
    status: "active",
    lastModified: "1 week ago",
    type: "Research",
    createdAt: "2023-11-15",
  },
  {
    id: 6,
    name: "Technical Support",
    description: "Handles technical issues and troubleshooting",
    calls: 112,
    avgRating: 4.4,
    status: "active",
    lastModified: "2 weeks ago",
    type: "Support",
    createdAt: "2023-11-20",
  },
  {
    id: 7,
    name: "Order Status Agent",
    description: "Provides updates on order status and shipping information",
    calls: 132,
    avgRating: 4.7,
    status: "active",
    lastModified: "2 weeks ago",
    type: "Support",
    createdAt: "2023-11-25",
  },
  {
    id: 8,
    name: "Lead Qualification Bot",
    description: "Qualifies inbound leads based on criteria",
    calls: 0,
    avgRating: 0,
    status: "draft",
    lastModified: "1 day ago",
    type: "Sales",
    createdAt: "2023-12-01",
  },
  {
    id: 9,
    name: "Customer Onboarding",
    description: "Guides new customers through product setup and onboarding",
    calls: 0,
    avgRating: 0,
    status: "draft",
    lastModified: "3 days ago",
    type: "Support",
    createdAt: "2023-12-05",
  },
  {
    id: 10,
    name: "Renewal Specialist",
    description: "Handles subscription renewals and upgrades",
    calls: 45,
    avgRating: 4.2,
    status: "paused",
    lastModified: "1 week ago",
    type: "Sales",
    createdAt: "2023-12-10",
  },
];
