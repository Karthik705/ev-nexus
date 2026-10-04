import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000/api';

export interface NegotiateRequest {
    driver_message: string;
    soc: number;
    battery_capacity: number;
    max_charging_rate: number;
    budget: number;
    force_fallback?: boolean;
}

export interface NegotiateResponse {
    ev_id: number;
    llm_result: any;
    validation_result: any;
    assigned_port: number | null;
    status: string;
    fallback_used: boolean;
    priority_score: number;
}

export interface StationStatus {
    ports: any[];
    queue: any[];
    metrics: {
        completed: number;
        revenue: number;
    };
}

/* ─── v2 scheduling comparison ──────────────────────────────────────── */

export interface ScenarioInfo {
    key: string;
    message: string;
    true_deadline_min: number | null;
    true_urgency: string;
    required_kwh: number | null;
    wants_full_charge: boolean;
    is_unverified_claim: boolean;
    notes: string;
    extracted: {
        urgency_level: string;
        deadline_minutes: number | null;
        reason_category: string;
        claimed_constraints: string[];
        confidence: number;
        explanation: string;
    } | null;
}

export interface ScenarioCatalogue {
    scenarios: ScenarioInfo[];
    policies: Record<string, { label: string; family: string }>;
    default_station: number[];
    extraction_quality: Record<string, any>;
}

export interface TimelineRow {
    ev_id: number;
    port_id: number | null;
    start_min: number | null;
    end_min: number | null;
    arrival_min: number;
    scenario_key: string;
    message: string;
    true_urgency: string;
    believed_urgency: string;
    contradiction_flagged: boolean;
    true_deadline_abs: number | null;
    believed_deadline_min: number | null;
    met_deadline: boolean | null;
    energy_kwh: number;
    cost: number;
    wait_min: number;
    soc_start: number;
    status: string;
}

export interface PolicyMetrics {
    policy: string;
    label: string;
    family: string;
    arrived: number;
    served: number;
    served_rate: number;
    deadline_evs: number;
    deadline_on_time: number;
    on_time_rate: number;
    deadline_miss_rate: number;
    mean_lateness_min: number;
    critical_deadline_evs: number;
    critical_on_time_rate: number;
    avg_wait_min: number;
    p95_wait_min: number;
    max_wait_min: number;
    energy_kwh: number;
    revenue: number;
    port_utilisation: number;
    unverified_claim_fast_port_minutes: number;
    contradictions_flagged: number;
}

export interface CompareInput {
    ev_id: number;
    arrival_min: number;
    scenario_key: string;
    message: string;
    soc: number;
    battery_kwh: number;
    max_rate_kw: number;
    budget: number;
    true_deadline_min: number | null;
    true_urgency: string;
    is_unverified_claim: boolean;
}

export interface CompareResponse {
    config: {
        station_kw: number[];
        num_ports: number;
        horizon_min: number;
        sim_horizon_min: number;
        num_evs: number;
        seed: number | null;
        arrivals_per_hour: number | null;
        engine: string;
        repeats: number;
        metrics_note: string;
    };
    inputs: CompareInput[];
    policies: Record<string, {
        label: string;
        family: string;
        metrics: PolicyMetrics;
        timeline: TimelineRow[];
        unserved: any[];
    }>;
    agent_vs?: Record<string, {
        label: string;
        on_time_rate_pp: number;
        critical_on_time_pp: number;
        avg_wait_min: number;
        p95_wait_min: number;
        served: number;
    }>;
}

export interface CompareRequestBody {
    evs?: Array<{
        scenario_key: string;
        soc: number;
        battery_capacity: number;
        max_charging_rate: number;
        budget: number;
        arrival_min: number;
    }>;
    seed?: number;
    arrivals_per_hour?: number;
    horizon_min?: number;
    station?: number[];
    policies?: string[];
    repeats?: number;
}

export const api = {
    negotiate: async (req: NegotiateRequest): Promise<NegotiateResponse> => {
        const res = await axios.post(`${API_BASE}/negotiate`, req);
        return res.data;
    },
    getStationStatus: async (): Promise<StationStatus> => {
        const res = await axios.get(`${API_BASE}/station`);
        return res.data;
    },
    stepSimulation: async (): Promise<StationStatus> => {
        const res = await axios.post(`${API_BASE}/step`);
        return res.data;
    },
    getBenchmarks: async (): Promise<any> => {
        const res = await axios.get(`${API_BASE}/benchmarks`);
        return res.data;
    },
    resetSimulation: async (): Promise<any> => {
        const res = await axios.post(`${API_BASE}/reset`);
        return res.data;
    },
    getScenarios: async (): Promise<ScenarioCatalogue> => {
        const res = await axios.get(`${API_BASE}/scenarios`);
        return res.data;
    },
    compare: async (body: CompareRequestBody): Promise<CompareResponse> => {
        const res = await axios.post(`${API_BASE}/compare`, body, { timeout: 60000 });
        return res.data;
    },
    checkHealth: async (): Promise<boolean> => {
        try {
            const res = await axios.get(`${API_BASE}/health`, { timeout: 3000 });
            return res.status === 200;
        } catch {
            return false;
        }
    }
};
