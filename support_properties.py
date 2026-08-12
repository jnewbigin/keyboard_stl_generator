from dataclasses import dataclass

from parameters import Parameters


@dataclass(frozen=True)
class SupportProperties:
    plate_thickness: float
    support_bar_height: float
    support_bar_width: float
    support_bar_fillet: float = 0.0
    set_to_origin: bool = True

    @classmethod
    def from_parameters(
        cls, parameters: Parameters, set_to_origin: bool = True
    ) -> SupportProperties:
        return cls(
            plate_thickness=parameters.plate_thickness,
            support_bar_height=parameters.support_bar_height,
            support_bar_width=parameters.support_bar_width,
            support_bar_fillet=parameters.support_bar_fillet,
            set_to_origin=set_to_origin,
        )
