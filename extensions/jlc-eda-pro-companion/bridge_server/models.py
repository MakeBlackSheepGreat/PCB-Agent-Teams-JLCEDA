"""
Pydantic models for bridge server request/response.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, AliasChoices


class PadData(BaseModel):
    number: str
    x: float
    y: float
    net: str
    layer: int
    shape: str = "round"
    width: float = 0
    height: float = 0
    drill: float = 0
    rotation: float = 0


class ComponentData(BaseModel):
    designator: str
    x: float
    y: float
    layer: int = 1
    rotation: float = 0
    pads: List[PadData] = []


class TrackData(BaseModel):
    net: str
    layer: int
    startX: float
    startY: float
    endX: float
    endY: float
    width: float


class ViaData(BaseModel):
    net: str
    x: float
    y: float
    holeDiameter: float
    diameter: float
    startLayer: int = 1
    endLayer: int = 2


class OutlinePoint(BaseModel):
    x: float
    y: float


class OutlineLineSegment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    startX: float = Field(validation_alias=AliasChoices('startX', 'start_x'))
    startY: float = Field(validation_alias=AliasChoices('startY', 'start_y'))
    endX: float = Field(validation_alias=AliasChoices('endX', 'end_x'))
    endY: float = Field(validation_alias=AliasChoices('endY', 'end_y'))


class OutlineArcSegment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    startX: float = Field(validation_alias=AliasChoices('startX', 'start_x'))
    startY: float = Field(validation_alias=AliasChoices('startY', 'start_y'))
    endX: float = Field(validation_alias=AliasChoices('endX', 'end_x'))
    endY: float = Field(validation_alias=AliasChoices('endY', 'end_y'))
    arcAngle: float = Field(default=0, validation_alias=AliasChoices('arcAngle', 'arc_angle'))


class StackupLayer(BaseModel):
    name: str = ""
    thickness: float = 0.035  # mm, default 1oz copper
    material: str = "copper"
    epsilon: float = 0.0  # dielectric constant (0 for copper layers)


class BoardData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    layers: List[int] = [1, 2]
    outline: List[OutlinePoint] = []
    outline_lines: List[OutlineLineSegment] = Field(default=[], validation_alias=AliasChoices('outline_lines', 'outlineLines'))
    outline_arcs: List[OutlineArcSegment] = Field(default=[], validation_alias=AliasChoices('outline_arcs', 'outlineArcs'))
    stackup: List[StackupLayer] = []
    board_thickness: float = Field(default=1.6, validation_alias=AliasChoices('board_thickness', 'boardThickness'))


class DiffPairConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    pair_gap: float = Field(default=0.101, validation_alias=AliasChoices('pair_gap', 'pairGap'))
    centerline_setback: float = Field(default=0, validation_alias=AliasChoices('centerline_setback', 'centerlineSetback'))
    min_turning_radius: float = Field(default=0.2, validation_alias=AliasChoices('min_turning_radius', 'minTurningRadius'))
    max_turn_angle: float = Field(default=180, validation_alias=AliasChoices('max_turn_angle', 'maxTurnAngle'))
    max_setback_angle: float = Field(default=45, validation_alias=AliasChoices('max_setback_angle', 'maxSetbackAngle'))
    fix_polarity: bool = Field(default=True, validation_alias=AliasChoices('fix_polarity', 'fixPolarity'))
    gnd_via_enabled: bool = Field(default=True, validation_alias=AliasChoices('gnd_via_enabled', 'gndViaEnabled'))


class RoutingConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    routing_mode: str = Field(default="single_ended", validation_alias=AliasChoices('routing_mode', 'routingMode'))
    nets_to_route: List[str] = ["*"]
    track_width: float = 10
    clearance: float = 8
    via_size: float = 24
    via_drill: float = 12
    layers_to_use: List[int] = [1, 2]
    grid_step: float = 6
    via_cost: int = 30
    max_ripup: int = 5
    stub_layer_swap: bool = True
    power_nets: str = ""
    power_widths: str = ""
    layer_costs: str = ""
    diff_pair: DiffPairConfig = Field(default=DiffPairConfig(), validation_alias=AliasChoices('diff_pair', 'diffPair'))
    bga_component: str = Field(default="", validation_alias=AliasChoices('bga_component', 'bgaComponent'))
    bga_exit_margin: float = Field(default=0, validation_alias=AliasChoices('bga_exit_margin', 'bgaExitMargin'))
    board_edge_clearance: float = 0
    plane_layers: List[int] = []
    plane_nets: List[str] = []
    units_mm: bool = False
    kicad_file_path: str = ""


class PCBJsonData(BaseModel):
    board: BoardData = BoardData()
    components: List[ComponentData] = []
    nets: List[str] = []
    existing_tracks: List[TrackData] = []
    existing_vias: List[ViaData] = []
    routing_config: RoutingConfig = RoutingConfig()


class RoutingStats(BaseModel):
    nets_routed: int = 0
    nets_failed: int = 0
    tracks_added: int = 0
    vias_added: int = 0
    time_seconds: float = 0


class RoutingResult(BaseModel):
    status: str = "pending"
    stats: RoutingStats = RoutingStats()
    tracks: List[TrackData] = []
    vias: List[ViaData] = []
    error: Optional[str] = None
