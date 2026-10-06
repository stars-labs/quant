const reasons: Record<string, [string, string]> = {
	pending_reconciliation: ['Waiting for confirmation of an existing order', '等待已有订单确认'],
	exit_submitted: ['Exit order submitted', '已提交退出订单'],
	entry_submitted: ['Buy order submitted', '已提交买入订单'],
	below_exchange_minimum: ['Amount is below the exchange minimum', '金额低于交易所最小下单要求'],
	no_entry_signal: ['No entry signal', '没有入场信号'],
	target_already_processed: ['This signal has already been processed', '此信号已处理'],
	confirmed_budget_unavailable: ['No confirmed budget is available', '没有可用的已确认预算'],
	entries_disabled: ['New entries are disabled', '已关闭新增买入'],
	no_dca_signal: ['No DCA instruction is available', '暂无定投指令'],
	today_already_processed: ["Today's DCA has already been processed", '今日定投已处理'],
	reconciliation_failed: [
		'Order reconciliation failed; check the owner runner',
		'订单核对失败，请检查执行器'
	],
	signal_feed_failed: ['Signal data is unavailable or invalid', '信号数据不可用或无效'],
	execution_failed: [
		'Execution checks failed; run local diagnostics',
		'执行检查失败，请运行本地诊断'
	]
};

export function decisionText(reason: string, lang: string): string {
	return (
		reasons[reason]?.[lang === 'zh' ? 1 : 0] ??
		(lang === 'zh' ? '请检查执行器诊断' : 'Check the owner runner diagnostics')
	);
}
