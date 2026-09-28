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
    checkHealth: async (): Promise<boolean> => {
        try {
            const res = await axios.get(`${API_BASE}/health`, { timeout: 3000 });
            return res.status === 200;
        } catch {
            return false;
        }
    }
};
