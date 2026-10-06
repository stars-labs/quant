const reasons: Record<string, [string, string]> = {
	insufficient_observations: [
		'Waiting for at least two recorded valuations.',
		'等待至少两次估值记录。'
	],
	unknown_flow_timing: ['Cash-flow confirmation times are missing.', '缺少资金确认时间。'],
	unreconciled_cash_flows: [
		'Recorded cash flows do not reconcile with valuations.',
		'资金流水与估值记录尚未核对一致。'
	],
	nonpositive_capital: [
		'No positive invested capital is available for this calculation.',
		'没有可用于计算的正值投入资本。'
	],
	invalid_valuation: ['Recorded valuations need review.', '估值记录需要检查。'],
	invalid_observation_times: ['Recorded observation times need review.', '估值时间需要检查。'],
	invalid_cash_flow: ['Recorded cash flows need review.', '资金流水需要检查。'],
	invalid_timestamps_or_amounts: [
		'Recorded times or amounts need review.',
		'记录的时间或金额需要检查。'
	],
	invalid_return: [
		'This period cannot produce a reliable return estimate.',
		'当前区间无法得到可靠收益率估算。'
	]
};
export function returnReason(reason: string | null, lang: string): string {
	return (
		reasons[reason ?? '']?.[lang === 'zh' ? 1 : 0] ??
		(lang === 'zh' ? '历史记录需要检查。' : 'Recorded history needs review.')
	);
}
