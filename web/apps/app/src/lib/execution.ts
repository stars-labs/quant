import { CONFIG } from './config';
import { getToken } from './auth';

export interface RunnerPosition {
	strategy: 'trend' | 'dca';
	asset: string;
	quantity: number;
	price_usdt: number;
	cost_usdt: number;
	realized_pnl_usdt: number;
}
export interface RunnerFill {
	client_id: string;
	strategy: 'trend' | 'dca';
	asset: string;
	side: 'buy' | 'sell';
	quantity: number;
	quote_usdt: number;
	fee_usdt: number;
	fee_rate: number;
	finished_at: string;
}
export interface RunnerDecision {
	strategy: 'account' | 'trend' | 'dca';
	asset: string | null;
	reason: string;
}
export interface RunnerHistoryPoint {
	observed_at: string;
	price_as_of: string;
	equity_usdt: number;
	cash_usdt: number;
	net_contributions_usdt: number;
	fees_usdt: number;
	net_pnl_usdt: number;
}
export interface RunnerAttribution {
	strategy: 'trend' | 'dca';
	asset: string;
	realized_pnl_usdt: number;
	unrealized_pnl_usdt: number;
	net_pnl_usdt: number;
	fees_usdt: number;
}
export interface RunnerReport {
	version: number;
	sequence: number;
	observed_at: string;
	status: 'healthy' | 'paused' | 'pending' | 'stale';
	venue: string;
	environment: string;
	cash_usdt: number;
	equity_usdt: number;
	funded_usdt: number;
	trend_available_usdt: number;
	dca_available_usdt: number;
	fees_usdt: number;
	positions: RunnerPosition[];
	fills: RunnerFill[];
	decisions?: RunnerDecision[];
	history?: RunnerHistoryPoint[];
	attribution?: RunnerAttribution[];
}
export interface RunnerConnection {
	id: string;
	label: string;
	venue: 'htx' | 'gate';
	environment: 'dry_run' | 'live';
	created_at: string;
	revoked_at: string | null;
	received_at: string | null;
	sequence: number;
	report: RunnerReport | null;
}

async function request<T>(path: string, body?: unknown): Promise<T> {
	const token = getToken();
	if (!token) throw new Error('Sign in to view your connected accounts.');
	const response = await fetch(`${CONFIG.API_BASE}${path}`, {
		method: body === undefined ? 'GET' : 'POST',
		headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
		...(body === undefined ? {} : { body: JSON.stringify(body) })
	});
	if (!response.ok) {
		throw new Error(
			response.status === 401 || response.status === 403
				? 'Your sign-in expired. Please sign in again.'
				: 'The display connection could not be updated. Please try again.'
		);
	}
	return response.json() as Promise<T>;
}

export const execution = {
	connections: () => request<RunnerConnection[]>('/runner_connections?order=created_at.desc'),
	create: (label: string, environment: 'dry_run' | 'live') =>
		request<{ id: string; upload_token: string }>('/rpc/create_runner_connection', {
			label,
			venue: 'htx',
			environment
		}),
	revoke: (id: string) => request<boolean>('/rpc/revoke_runner_connection', { connection_id: id })
};
