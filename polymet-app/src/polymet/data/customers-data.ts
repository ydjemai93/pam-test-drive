export interface Customer {
  id: number;
  name: string;
  email: string;
  phoneNumber: string;
  company?: string;
  status: "active" | "inactive" | "lead" | "churned";
  totalCalls: number;
  lastContact: string;
  tags: string[];
  notes?: string;
  avatar?: string;
  location?: string;
  createdAt: string;
}

export const CUSTOMERS_DATA: Customer[] = [
  {
    id: 101,
    name: "John Smith",
    email: "john.smith@example.com",
    phoneNumber: "+1 (555) 123-4567",
    company: "Acme Corporation",
    status: "active",
    totalCalls: 12,
    lastContact: "2023-11-28T14:30:00Z",
    tags: ["enterprise", "billing"],
    notes: "Interested in upgrading to premium plan",
    avatar: "https://github.com/yusufhilmi.png",
    location: "New York, NY",
    createdAt: "2023-01-15T10:30:00Z",
  },
  {
    id: 102,
    name: "Emily Johnson",
    email: "emily.johnson@example.com",
    phoneNumber: "+1 (555) 234-5678",
    company: "Johnson & Co",
    status: "active",
    totalCalls: 8,
    lastContact: "2023-11-28T15:45:00Z",
    tags: ["enterprise", "demo"],
    notes: "Scheduled a demo for next Tuesday",
    avatar: "https://github.com/furkanksl.png",
    location: "San Francisco, CA",
    createdAt: "2023-02-20T14:15:00Z",
  },
  {
    id: 103,
    name: "Michael Brown",
    email: "michael.brown@example.com",
    phoneNumber: "+1 (555) 345-6789",
    company: "Brown Industries",
    status: "active",
    totalCalls: 5,
    lastContact: "2023-11-28T16:20:00Z",
    tags: ["installation", "support"],
    notes: "Confirmed appointment for service installation",
    avatar: "https://github.com/kdrnp.png",
    location: "Chicago, IL",
    createdAt: "2023-03-10T09:45:00Z",
  },
  {
    id: 104,
    name: "Sarah Davis",
    email: "sarah.davis@example.com",
    phoneNumber: "+1 (555) 456-7890",
    company: "Davis Tech",
    status: "inactive",
    totalCalls: 3,
    lastContact: "2023-11-28T17:05:00Z",
    tags: ["support", "technical"],
    notes: "Had issues with the platform, needs follow-up",
    avatar: "https://github.com/yahyabedirhan.png",
    location: "Austin, TX",
    createdAt: "2023-04-05T11:20:00Z",
  },
  {
    id: 105,
    name: "Robert Wilson",
    email: "robert.wilson@example.com",
    phoneNumber: "+1 (555) 567-8901",
    company: "Wilson Enterprises",
    status: "active",
    totalCalls: 15,
    lastContact: "2023-11-28T09:15:00Z",
    tags: ["enterprise", "pricing"],
    notes: "Interested in custom pricing for large team",
    avatar: "https://github.com/buyuktas18.png",
    location: "Seattle, WA",
    createdAt: "2023-01-25T13:10:00Z",
  },
  {
    id: 106,
    name: "Jennifer Taylor",
    email: "jennifer.taylor@example.com",
    phoneNumber: "+1 (555) 678-9012",
    company: "Taylor Solutions",
    status: "active",
    totalCalls: 7,
    lastContact: "2023-11-28T10:30:00Z",
    tags: ["appointment", "reschedule"],
    notes: "Rescheduled appointment to next week",
    avatar: "https://github.com/polymet-ai.png",
    location: "Boston, MA",
    createdAt: "2023-02-12T15:30:00Z",
  },
  {
    id: 107,
    name: "David Anderson",
    email: "david.anderson@example.com",
    phoneNumber: "+1 (555) 789-0123",
    company: "Anderson Group",
    status: "lead",
    totalCalls: 2,
    lastContact: "2023-11-28T11:20:00Z",
    tags: ["lead", "pricing"],
    notes: "Requested information about pricing plans",
    avatar: "https://github.com/yusufhilmi.png",
    location: "Denver, CO",
    createdAt: "2023-05-18T10:45:00Z",
  },
  {
    id: 108,
    name: "Lisa Martinez",
    email: "lisa.martinez@example.com",
    phoneNumber: "+1 (555) 890-1234",
    company: "Martinez LLC",
    status: "active",
    totalCalls: 10,
    lastContact: "2023-11-27T13:45:00Z",
    tags: ["integration", "technical"],
    notes: "Discussed integration options with current systems",
    avatar: "https://github.com/furkanksl.png",
    location: "Miami, FL",
    createdAt: "2023-03-22T09:15:00Z",
  },
  {
    id: 109,
    name: "Kevin Thompson",
    email: "kevin.thompson@example.com",
    phoneNumber: "+1 (555) 901-2345",
    company: "Thompson Consulting",
    status: "active",
    totalCalls: 6,
    lastContact: "2023-11-27T14:30:00Z",
    tags: ["consultation", "enterprise"],
    notes: "Scheduled initial consultation for team onboarding",
    avatar: "https://github.com/kdrnp.png",
    location: "Atlanta, GA",
    createdAt: "2023-04-14T14:20:00Z",
  },
  {
    id: 110,
    name: "Amanda White",
    email: "amanda.white@example.com",
    phoneNumber: "+1 (555) 012-3456",
    company: "White Innovations",
    status: "active",
    totalCalls: 9,
    lastContact: "2023-11-27T15:15:00Z",
    tags: ["billing", "support"],
    notes: "Had billing issue that was resolved",
    avatar: "https://github.com/yahyabedirhan.png",
    location: "Portland, OR",
    createdAt: "2023-02-28T11:30:00Z",
  },
  {
    id: 111,
    name: "Thomas Harris",
    email: "thomas.harris@example.com",
    phoneNumber: "+1 (555) 123-4567",
    company: "Harris Co",
    status: "churned",
    totalCalls: 4,
    lastContact: "2023-11-27T16:00:00Z",
    tags: ["churned", "competitor"],
    notes: "Decided to go with competitor solution",
    avatar: "https://github.com/buyuktas18.png",
    location: "Philadelphia, PA",
    createdAt: "2023-01-10T09:45:00Z",
  },
  {
    id: 112,
    name: "Nicole Clark",
    email: "nicole.clark@example.com",
    phoneNumber: "+1 (555) 234-5678",
    company: "Clark Industries",
    status: "active",
    totalCalls: 11,
    lastContact: "2023-11-26T10:20:00Z",
    tags: ["onboarding", "training"],
    notes: "Completed onboarding, scheduled training session",
    avatar: "https://github.com/polymet-ai.png",
    location: "San Diego, CA",
    createdAt: "2023-03-05T13:15:00Z",
  },
  {
    id: 113,
    name: "Daniel Lewis",
    email: "daniel.lewis@example.com",
    phoneNumber: "+1 (555) 345-6789",
    company: "Lewis Technologies",
    status: "lead",
    totalCalls: 3,
    lastContact: "2023-11-26T11:30:00Z",
    tags: ["lead", "enterprise"],
    notes: "Interested in enterprise plan, requested custom quote",
    avatar: "https://github.com/yusufhilmi.png",
    location: "Dallas, TX",
    createdAt: "2023-05-25T10:30:00Z",
  },
  {
    id: 114,
    name: "Michelle Walker",
    email: "michelle.walker@example.com",
    phoneNumber: "+1 (555) 456-7890",
    company: "Walker & Associates",
    status: "active",
    totalCalls: 7,
    lastContact: "2023-11-26T13:45:00Z",
    tags: ["demo", "pricing"],
    notes: "Scheduled product demo for team",
    avatar: "https://github.com/furkanksl.png",
    location: "Phoenix, AZ",
    createdAt: "2023-04-18T15:45:00Z",
  },
  {
    id: 115,
    name: "Christopher Hall",
    email: "christopher.hall@example.com",
    phoneNumber: "+1 (555) 567-8901",
    company: "Hall Digital",
    status: "inactive",
    totalCalls: 5,
    lastContact: "2023-11-26T14:50:00Z",
    tags: ["technical", "login"],
    notes: "Had login issues, needs technical support",
    avatar: "https://github.com/kdrnp.png",
    location: "Minneapolis, MN",
    createdAt: "2023-02-08T09:20:00Z",
  },
];

// Helper function to get customer by ID
export const getCustomerById = (id: number): Customer | undefined => {
  return CUSTOMERS_DATA.find((customer) => customer.id === id);
};

// Helper function to get customers by status
export const getCustomersByStatus = (
  status: Customer["status"]
): Customer[] => {
  return CUSTOMERS_DATA.filter((customer) => customer.status === status);
};

// Helper function to get customers by tag
export const getCustomersByTag = (tag: string): Customer[] => {
  return CUSTOMERS_DATA.filter((customer) => customer.tags.includes(tag));
};

// Helper function to get customers by company
export const getCustomersByCompany = (company: string): Customer[] => {
  return CUSTOMERS_DATA.filter((customer) =>
    customer.company?.toLowerCase().includes(company.toLowerCase())
  );
};

// Helper function to search customers
export const searchCustomers = (query: string): Customer[] => {
  const lowerCaseQuery = query.toLowerCase();

  return CUSTOMERS_DATA.filter(
    (customer) =>
      customer.name.toLowerCase().includes(lowerCaseQuery) ||
      customer.email.toLowerCase().includes(lowerCaseQuery) ||
      customer.phoneNumber.includes(query) ||
      (customer.company &&
        customer.company.toLowerCase().includes(lowerCaseQuery)) ||
      (customer.location &&
        customer.location.toLowerCase().includes(lowerCaseQuery))
  );
};
