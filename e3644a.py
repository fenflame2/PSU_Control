#!/usr/bin/env python3
"""E3644A single-output bench panel 0.3.0."""
import e3640a as shared
from supply import Serial
from single_models import E3644_RANGES, E3644Demo, E3644Instrument


def session(port):
    return E3644Instrument(Serial(port)) if port else E3644Demo()


class E3644Panel(shared.Panel):
    model = "E3644A"
    description = "DC POWER SUPPLY   /   80 W"
    ranges = E3644_RANGES
    connect = staticmethod(session)

    def front_keys(self):
        keys = super().front_keys()
        keys[:2] = [("8 V / 8 A",lambda:self.change_range("P8V")),
                    ("20 V / 4 A",lambda:self.change_range("P20V"))]
        return keys


if __name__ == "__main__":
    shared.main(E3644Panel)
