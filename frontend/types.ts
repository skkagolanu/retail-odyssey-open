export interface Product {
  id: string;
  name: string;
  brand: string;
  retailer: string;
  category: "top" | "bottom" | "layer" | "shoes" | "accessory";
  price_pence: number;
  currency: "GBP";
  tags: string[];
  url: string | null;
  captured_at: string;
}
export interface Preferences {
  occasion: string | null;
  style: string | null;
  budget_gbp: number | null;
}
export interface Catalogue {
  mode: "sample" | "snapshot";
  description: string;
  products: number;
  stock_verified: false;
}
export interface Turn {
  role: "user" | "assistant";
  content: string;
}
export interface AgentEvent {
  trace_id: string;
  sequence: number;
  agent: string;
  mode: string;
  status: string;
  duration_ms: number;
  handoff_keys: string[];
}
export interface TokenBudget {
  turn_input_limit: number;
  turn_output_limit: number;
  reserved_input_tokens: number;
  reserved_output_tokens: number;
  calls: {
    agent: string;
    dropped_history_messages: number;
    usage: { prompt_eval_count?: number; eval_count?: number };
  }[];
}
export interface Reply {
  trace_id: string;
  agent_trace: AgentEvent[];
  token_budget: TokenBudget;
  answer: string;
  products: Product[];
  catalogue: Catalogue;
  preferences: Preferences;
  warnings: string[];
  image: string | null;
  image_kind: "generated" | "schematic";
  engine: string;
  timings: {
    total_ms: number;
    stages: { name: string; duration_ms: number; status: string }[];
  };
}
export interface Session {
  history: Turn[];
  preferences: Preferences;
  history_limit: number;
  ttl_seconds: number;
  catalogue: Catalogue;
}
export interface Health {
  status: string;
  engine: string;
  model_available: boolean | null;
  image_generation_configured: boolean;
}
