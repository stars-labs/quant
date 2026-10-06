import assert from 'node:assert/strict';
import test from 'node:test';
import { decisionText } from './runnerDecisions.ts';

test('decision explanations respect the selected language', () => {
	assert.equal(
		decisionText('confirmed_budget_unavailable', 'en'),
		'No confirmed budget is available'
	);
	assert.equal(decisionText('confirmed_budget_unavailable', 'zh'), '没有可用的已确认预算');
});

test('unknown reasons never expose arbitrary report text', () => {
	assert.equal(decisionText('secret signed URL', 'en'), 'Check the owner runner diagnostics');
});
