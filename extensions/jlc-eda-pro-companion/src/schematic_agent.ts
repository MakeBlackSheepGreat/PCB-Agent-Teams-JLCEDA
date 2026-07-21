export type NetFlagKind = 'Power' | 'Ground' | 'AnalogGround' | 'ProtectGround';
export type NetPortDirection = 'IN' | 'OUT' | 'BI';

export interface SchematicComponentPlan {
	id: string;
	lcsc_id: string;
	x: number;
	y: number;
	rotation?: number;
	mirror?: boolean;
	designator?: string;
	name?: string;
	manufacturer?: string;
	manufacturer_id?: string;
	supplier?: string;
	add_into_bom?: boolean;
	add_into_pcb?: boolean;
}

export interface SchematicWirePlan {
	net: string;
	points: Array<[number, number]>;
}

export interface SchematicNetFlagPlan {
	kind: NetFlagKind;
	net: string;
	x: number;
	y: number;
	rotation?: number;
	mirror?: boolean;
}

export interface SchematicNetPortPlan {
	direction: NetPortDirection;
	net: string;
	x: number;
	y: number;
	rotation?: number;
	mirror?: boolean;
}

export interface SchematicPlan {
	version: 1;
	components: Array<SchematicComponentPlan>;
	wires?: Array<SchematicWirePlan>;
	net_flags?: Array<SchematicNetFlagPlan>;
	net_ports?: Array<SchematicNetPortPlan>;
	run_erc?: boolean;
	save?: boolean;
}

export interface PlanValidationResult {
	ok: boolean;
	plan?: SchematicPlan;
	errors: Array<string>;
	warnings: Array<string>;
}

export interface SchematicExecutionResult {
	ok: boolean;
	created: {
		components: number;
		wires: number;
		net_flags: number;
		net_ports: number;
	};
	resolved_components: Array<{ id: string; lcsc_id: string; device_name: string }>;
	erc?: { passed: boolean };
	netlist?: string;
	saved?: boolean;
	errors: Array<string>;
	warnings: Array<string>;
	rollback_attempted: boolean;
	rollback_succeeded?: boolean;
}

type EdaApi = any;

const MAX_COMPONENTS = 128;
const MAX_WIRES = 256;
const MAX_AUXILIARY_PRIMITIVES = 128;
const MAX_COORDINATE = 1_000_000;
const LCSC_ID = /^C\d+$/;
const IDENTIFIER = /^[A-Za-z][A-Za-z0-9_]*$/;
const NET_NAME = /^[A-Za-z0-9_+\-./]+$/;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteCoordinate(value: unknown): value is number {
	return typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= MAX_COORDINATE;
}

function isOptionalBoolean(value: unknown): boolean {
	return value === undefined || typeof value === 'boolean';
}

function isOptionalRotation(value: unknown): boolean {
	return value === undefined || isFiniteCoordinate(value);
}

function isText(value: unknown, maxLength = 180): value is string {
	return typeof value === 'string' && value.length > 0 && value.length <= maxLength;
}

function isValidNetName(value: unknown): value is string {
	return isText(value, 120) && NET_NAME.test(value);
}

function addOptionalStringErrors(value: Record<string, unknown>, field: string, errors: Array<string>): void {
	if (value[field] !== undefined && !isText(value[field])) {
		errors.push(`${field} must be a non-empty string no longer than 180 characters`);
	}
}

function getPlanArray(plan: Record<string, unknown>, field: string, errors: Array<string>): Array<unknown> {
	const value = plan[field];
	if (value === undefined) return [];
	if (!Array.isArray(value)) {
		errors.push(`${field} must be an array`);
		return [];
	}
	return value;
}

/**
 * Validate the deliberately small, reviewable input contract used by the
 * Schematic Agent. A plan must fully resolve before the extension writes any
 * primitive to the active schematic page.
 */
export function validateSchematicPlan(rawPlan: unknown): PlanValidationResult {
	const errors: Array<string> = [];
	const warnings: Array<string> = [];
	if (!isRecord(rawPlan)) {
		return { ok: false, errors: ['Plan must be a JSON object'], warnings };
	}
	if (rawPlan.version !== 1) errors.push('version must be 1');

	const rawComponents = getPlanArray(rawPlan, 'components', errors);
	const rawWires = getPlanArray(rawPlan, 'wires', errors);
	const rawNetFlags = getPlanArray(rawPlan, 'net_flags', errors);
	const rawNetPorts = getPlanArray(rawPlan, 'net_ports', errors);
	if (rawComponents.length > MAX_COMPONENTS) errors.push(`components cannot exceed ${MAX_COMPONENTS}`);
	if (rawWires.length > MAX_WIRES) errors.push(`wires cannot exceed ${MAX_WIRES}`);
	if (rawNetFlags.length + rawNetPorts.length > MAX_AUXILIARY_PRIMITIVES) {
		errors.push(`net_flags and net_ports combined cannot exceed ${MAX_AUXILIARY_PRIMITIVES}`);
	}
	if (!isOptionalBoolean(rawPlan.run_erc)) errors.push('run_erc must be a boolean');
	if (!isOptionalBoolean(rawPlan.save)) errors.push('save must be a boolean');

	const components: Array<SchematicComponentPlan> = [];
	const usedIds = new Set<string>();
	const usedDesignators = new Set<string>();
	for (const [index, rawComponent] of rawComponents.entries()) {
		const prefix = `components[${index}]`;
		if (!isRecord(rawComponent)) {
			errors.push(`${prefix} must be an object`);
			continue;
		}
		let componentId: string | undefined;
		if (!isText(rawComponent.id, 80) || !IDENTIFIER.test(rawComponent.id)) {
			errors.push(`${prefix}.id must use letters, digits, and underscores`);
		} else if (usedIds.has(rawComponent.id)) {
			errors.push(`${prefix}.id duplicates ${rawComponent.id}`);
		} else {
			componentId = rawComponent.id;
			usedIds.add(rawComponent.id);
		}
		if (!isText(rawComponent.lcsc_id, 40) || !LCSC_ID.test(rawComponent.lcsc_id)) {
			errors.push(`${prefix}.lcsc_id must be an LCSC C number`);
		}
		if (!isFiniteCoordinate(rawComponent.x) || !isFiniteCoordinate(rawComponent.y)) {
			errors.push(`${prefix}.x and ${prefix}.y must be finite coordinates`);
		}
		if (!isOptionalRotation(rawComponent.rotation)) errors.push(`${prefix}.rotation must be a finite number`);
		if (!isOptionalBoolean(rawComponent.mirror)) errors.push(`${prefix}.mirror must be a boolean`);
		if (!isOptionalBoolean(rawComponent.add_into_bom)) errors.push(`${prefix}.add_into_bom must be a boolean`);
		if (!isOptionalBoolean(rawComponent.add_into_pcb)) errors.push(`${prefix}.add_into_pcb must be a boolean`);
		addOptionalStringErrors(rawComponent, 'name', errors);
		addOptionalStringErrors(rawComponent, 'manufacturer', errors);
		addOptionalStringErrors(rawComponent, 'manufacturer_id', errors);
		addOptionalStringErrors(rawComponent, 'supplier', errors);
		const plannedDesignator = rawComponent.designator ?? componentId;
		if (plannedDesignator !== undefined) {
			if (!isText(plannedDesignator, 80) || !IDENTIFIER.test(plannedDesignator)) {
				errors.push(`${prefix}.designator must use letters, digits, and underscores`);
			} else if (usedDesignators.has(plannedDesignator)) {
				errors.push(`${prefix}.designator duplicates ${plannedDesignator}`);
			} else {
				usedDesignators.add(plannedDesignator);
			}
		}
		components.push(rawComponent as unknown as SchematicComponentPlan);
	}

	const wires: Array<SchematicWirePlan> = [];
	for (const [index, rawWire] of rawWires.entries()) {
		const prefix = `wires[${index}]`;
		if (!isRecord(rawWire)) {
			errors.push(`${prefix} must be an object`);
			continue;
		}
		if (!isValidNetName(rawWire.net)) errors.push(`${prefix}.net contains unsupported characters`);
		if (!Array.isArray(rawWire.points) || rawWire.points.length < 2) {
			errors.push(`${prefix}.points must contain at least two coordinate pairs`);
			continue;
		}
		for (const [pointIndex, rawPoint] of rawWire.points.entries()) {
			if (!Array.isArray(rawPoint) || rawPoint.length !== 2 || !isFiniteCoordinate(rawPoint[0]) || !isFiniteCoordinate(rawPoint[1])) {
				errors.push(`${prefix}.points[${pointIndex}] must be [x, y] finite coordinates`);
			}
		}
		wires.push(rawWire as unknown as SchematicWirePlan);
	}

	const netFlags: Array<SchematicNetFlagPlan> = [];
	for (const [index, rawFlag] of rawNetFlags.entries()) {
		const prefix = `net_flags[${index}]`;
		if (!isRecord(rawFlag)) {
			errors.push(`${prefix} must be an object`);
			continue;
		}
		if (!['Power', 'Ground', 'AnalogGround', 'ProtectGround'].includes(String(rawFlag.kind))) {
			errors.push(`${prefix}.kind is unsupported`);
		}
		if (!isValidNetName(rawFlag.net)) errors.push(`${prefix}.net contains unsupported characters`);
		if (!isFiniteCoordinate(rawFlag.x) || !isFiniteCoordinate(rawFlag.y)) errors.push(`${prefix}.x and ${prefix}.y must be finite coordinates`);
		if (!isOptionalRotation(rawFlag.rotation)) errors.push(`${prefix}.rotation must be a finite number`);
		if (!isOptionalBoolean(rawFlag.mirror)) errors.push(`${prefix}.mirror must be a boolean`);
		netFlags.push(rawFlag as unknown as SchematicNetFlagPlan);
	}

	const netPorts: Array<SchematicNetPortPlan> = [];
	for (const [index, rawPort] of rawNetPorts.entries()) {
		const prefix = `net_ports[${index}]`;
		if (!isRecord(rawPort)) {
			errors.push(`${prefix} must be an object`);
			continue;
		}
		if (!['IN', 'OUT', 'BI'].includes(String(rawPort.direction))) errors.push(`${prefix}.direction is unsupported`);
		if (!isValidNetName(rawPort.net)) errors.push(`${prefix}.net contains unsupported characters`);
		if (!isFiniteCoordinate(rawPort.x) || !isFiniteCoordinate(rawPort.y)) errors.push(`${prefix}.x and ${prefix}.y must be finite coordinates`);
		if (!isOptionalRotation(rawPort.rotation)) errors.push(`${prefix}.rotation must be a finite number`);
		if (!isOptionalBoolean(rawPort.mirror)) errors.push(`${prefix}.mirror must be a boolean`);
		netPorts.push(rawPort as unknown as SchematicNetPortPlan);
	}

	if (components.length === 0) warnings.push('Plan contains no components');
	if (wires.length === 0) warnings.push('Plan contains no wires');
	if (netFlags.length === 0 && netPorts.length === 0) warnings.push('Plan contains no net flags or ports');
	if (errors.length > 0) return { ok: false, errors, warnings };

	return {
		ok: true,
		plan: {
			version: 1,
			components,
			wires,
			net_flags: netFlags,
			net_ports: netPorts,
			run_erc: rawPlan.run_erc !== false,
			save: rawPlan.save !== false,
		},
		errors,
		warnings,
	};
}

export function summarizeSchematicPlan(rawPlan: unknown): PlanValidationResult & { summary?: Record<string, number> } {
	const validation = validateSchematicPlan(rawPlan);
	if (!validation.plan) return validation;
	return {
		...validation,
		summary: {
			components: validation.plan.components.length,
			wires: validation.plan.wires?.length ?? 0,
			net_flags: validation.plan.net_flags?.length ?? 0,
			net_ports: validation.plan.net_ports?.length ?? 0,
		},
	};
}

function getPrimitiveId(primitive: any): string | undefined {
	if (primitive && typeof primitive.getState_PrimitiveId === 'function') return primitive.getState_PrimitiveId();
	return primitive?.primitiveId ?? primitive?.id;
}

function flattenWirePoints(points: Array<[number, number]>): Array<number> {
	return points.flatMap(([x, y]) => [x, y]);
}

function requireSchematicApi(edaApi: EdaApi): void {
	if (!edaApi?.lib_Device?.getByLcscIds || !edaApi?.sch_PrimitiveComponent?.create || !edaApi?.sch_PrimitiveWire?.create) {
		throw new Error('The current EasyEDA Pro version does not expose the required schematic extension APIs');
	}
}

async function resolveComponent(edaApi: EdaApi, lcscId: string): Promise<any | undefined> {
	const result = await edaApi.lib_Device.getByLcscIds(lcscId);
	const items = Array.isArray(result) ? result : result ? [result] : [];
	return items.find((item) => item?.uuid && item?.libraryUuid);
}

async function rollbackCreatedPrimitives(edaApi: EdaApi, created: Array<{ api: any; primitive: any }>): Promise<boolean> {
	let succeeded = true;
	for (const item of [...created].reverse()) {
		try {
			const primitiveId = getPrimitiveId(item.primitive);
			const deleted = await item.api.delete(primitiveId ?? item.primitive);
			if (!deleted) succeeded = false;
		} catch {
			succeeded = false;
		}
	}
	return succeeded;
}

/**
 * Apply a resolved design plan to the currently active EasyEDA Pro schematic.
 * Catalog lookup is performed before any write. Runtime failures remove every
 * primitive created by this invocation whenever the Pro API allows it.
 */
export async function applySchematicPlan(edaApi: EdaApi, rawPlan: unknown): Promise<SchematicExecutionResult> {
	const validation = validateSchematicPlan(rawPlan);
	const emptyCreated = { components: 0, wires: 0, net_flags: 0, net_ports: 0 };
	if (!validation.ok || !validation.plan) {
		return {
			ok: false,
			created: emptyCreated,
			resolved_components: [],
			errors: validation.errors,
			warnings: validation.warnings,
			rollback_attempted: false,
		};
	}

	const result: SchematicExecutionResult = {
		ok: false,
		created: emptyCreated,
		resolved_components: [],
		errors: [],
		warnings: [...validation.warnings],
		rollback_attempted: false,
	};
	const created: Array<{ api: any; primitive: any }> = [];

	try {
		requireSchematicApi(edaApi);
		const resolved = new Map<string, any>();
		for (const component of validation.plan.components) {
			const device = await resolveComponent(edaApi, component.lcsc_id);
			if (!device) throw new Error(`${component.id}: LCSC part ${component.lcsc_id} is unavailable in the EasyEDA Pro library`);
			resolved.set(component.id, device);
			result.resolved_components.push({ id: component.id, lcsc_id: component.lcsc_id, device_name: String(device.name ?? component.lcsc_id) });
		}

		for (const component of validation.plan.components) {
			const device = resolved.get(component.id);
			const primitive = await edaApi.sch_PrimitiveComponent.create(
				device, component.x, component.y, undefined, component.rotation ?? 0, component.mirror ?? false,
				component.add_into_bom ?? true, component.add_into_pcb ?? true,
			);
			if (!primitive) throw new Error(`${component.id}: EasyEDA Pro rejected component placement`);
			created.push({ api: edaApi.sch_PrimitiveComponent, primitive });
			const property: Record<string, unknown> = {
				designator: component.designator ?? component.id,
				addIntoBom: component.add_into_bom ?? true,
				addIntoPcb: component.add_into_pcb ?? true,
				supplierId: component.lcsc_id,
			};
			if (component.name !== undefined) property.name = component.name;
			if (component.manufacturer !== undefined) property.manufacturer = component.manufacturer;
			if (component.manufacturer_id !== undefined) property.manufacturerId = component.manufacturer_id;
			if (component.supplier !== undefined) property.supplier = component.supplier;
			const updated = await edaApi.sch_PrimitiveComponent.modify(primitive, property);
			if (!updated) throw new Error(`${component.id}: EasyEDA Pro rejected component properties`);
			result.created.components += 1;
		}

		for (const wire of validation.plan.wires ?? []) {
			const primitive = await edaApi.sch_PrimitiveWire.create(flattenWirePoints(wire.points), wire.net, null, null, null);
			if (!primitive) throw new Error(`Wire for net ${wire.net} was rejected`);
			created.push({ api: edaApi.sch_PrimitiveWire, primitive });
			result.created.wires += 1;
		}

		for (const flag of validation.plan.net_flags ?? []) {
			const primitive = await edaApi.sch_PrimitiveComponent.createNetFlag(flag.kind, flag.net, flag.x, flag.y, flag.rotation ?? 0, flag.mirror ?? false);
			if (!primitive) throw new Error(`Net flag for ${flag.net} was rejected`);
			created.push({ api: edaApi.sch_PrimitiveComponent, primitive });
			result.created.net_flags += 1;
		}

		for (const port of validation.plan.net_ports ?? []) {
			const primitive = await edaApi.sch_PrimitiveComponent.createNetPort(port.direction, port.net, port.x, port.y, port.rotation ?? 0, port.mirror ?? false);
			if (!primitive) throw new Error(`Net port for ${port.net} was rejected`);
			created.push({ api: edaApi.sch_PrimitiveComponent, primitive });
			result.created.net_ports += 1;
		}

		if (validation.plan.run_erc && edaApi.sch_Drc?.check) {
			result.erc = { passed: await edaApi.sch_Drc.check(true, false) };
			if (!result.erc.passed) result.warnings.push('ERC returned warnings or errors; review the EasyEDA Pro DRC panel before PCB transfer');
		}
		if (edaApi.sch_Netlist?.getNetlist) result.netlist = await edaApi.sch_Netlist.getNetlist();
		if (validation.plan.save) {
			result.saved = await edaApi.sch_Document.save();
			if (!result.saved) throw new Error('EasyEDA Pro could not save the schematic document');
		}
		result.ok = true;
		return result;
	} catch (error: unknown) {
		result.errors.push(error instanceof Error ? error.message : String(error));
		if (created.length > 0) {
			result.rollback_attempted = true;
			result.rollback_succeeded = await rollbackCreatedPrimitives(edaApi, created);
			if (!result.rollback_succeeded) result.warnings.push('Rollback did not remove every created primitive; inspect the active schematic before retrying');
		}
		return result;
	}
}
