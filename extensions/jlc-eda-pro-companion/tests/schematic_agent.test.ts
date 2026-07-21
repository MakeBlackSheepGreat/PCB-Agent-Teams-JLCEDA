import assert from 'node:assert/strict';

import { applySchematicPlan, validateSchematicPlan } from '../src/schematic_agent';

const validPlan = {
	version: 1,
	components: [{ id: 'R1', lcsc_id: 'C25804', x: 1000, y: 1000, name: '10k' }],
	wires: [{ net: 'VIN', points: [[900, 1000], [1000, 1000]] }],
	net_flags: [],
	net_ports: [],
	run_erc: true,
	save: true,
};

function createMockApi(rejectPropertyWrite = false): { api: any; getDeleted: () => number } {
	let sequence = 0;
	let deleted = 0;
	const primitive = () => ({ getState_PrimitiveId: () => String(++sequence) });
	const deletePrimitive = async () => {
		deleted += 1;
		return true;
	};
	return {
		api: {
			lib_Device: { getByLcscIds: async () => [{ uuid: 'device', libraryUuid: 'library', name: '10k resistor' }] },
			sch_PrimitiveComponent: {
				create: async () => primitive(),
				modify: async (item: unknown) => (rejectPropertyWrite ? undefined : item),
				createNetFlag: async () => primitive(),
				createNetPort: async () => primitive(),
				delete: deletePrimitive,
			},
			sch_PrimitiveWire: { create: async () => primitive(), delete: deletePrimitive },
			sch_Drc: { check: async () => true },
			sch_Netlist: { getNetlist: async () => '(netlist)' },
			sch_Document: { save: async () => true },
		},
		getDeleted: () => deleted,
	};
}

async function main(): Promise<void> {
	assert.equal(validateSchematicPlan(validPlan).ok, true);
	assert.equal(
		validateSchematicPlan({
			...validPlan,
			components: [...validPlan.components, { id: 'R2', designator: 'R1', lcsc_id: 'C25804', x: 1200, y: 1000 }],
		}).ok,
		false,
	);

	const success = createMockApi();
	const result = await applySchematicPlan(success.api, validPlan);
	assert.equal(result.ok, true);
	assert.equal(result.created.components, 1);
	assert.equal(result.created.wires, 1);
	assert.equal(result.erc?.passed, true);
	assert.equal(result.saved, true);

	const rollback = createMockApi(true);
	const failedResult = await applySchematicPlan(rollback.api, validPlan);
	assert.equal(failedResult.ok, false);
	assert.equal(failedResult.rollback_attempted, true);
	assert.equal(failedResult.rollback_succeeded, true);
	assert.equal(rollback.getDeleted(), 1);
}

main().then(
	() => console.log('schematic-agent tests passed'),
	(error: unknown) => {
		console.error(error);
		process.exitCode = 1;
	},
);
