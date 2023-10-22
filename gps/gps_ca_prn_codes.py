from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import max_len_seq, resample


@dataclass
class ChipDelayMs:
    """New-type to represent the delay assigned to a given GPS satellite PRN.
    Each chip is transmitted over 1 millisecond, so the chip delay is directly expressed in milliseconds.
    """
    delay_ms: int

    def __init__(self, delay_ms: int) -> None:
        self.delay_ms = delay_ms


@dataclass
class G2SequenceTapsConfiguration:
    taps: list[int]

    def __init__(self, taps: list[int]) -> None:
        self.taps = taps


@dataclass
class GpsSatelliteId:
    """New-type to semantically store GPS satellite IDs by their PRN signal ID"""
    id: int

    def __init__(self, id: int) -> None:
        self.id = id

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, type(self)):
            return False
        # <class '                 gps.gps_ca_prn_codes.GpsSatelliteId'>
        # <class 'gps_project_name.gps.gps_ca_prn_codes.GpsSatelliteId'>
        return self.id == other.id


@dataclass
class GpsReplicaPrnSignal:
    """New-type to semantically store the 'replica' PRN signal for a given satellite"""
    inner: np.ndarray


def _generate_ca_code_rolled_by(delay_ms: int) -> np.ndarray:
    """Generate the C/A code by generating the 'G1' and 'G2' sequences, then mixing them.
    Note that we generate the 'pure' G2 code, then roll it by `delay_ms` chips before mixing. This code is only ever
    used in the context of the PRN for a particular GPS satellite, so we don't need to access it pre-roll (though it's
    fine to pass `delay_ms=0` if this is desired.

    Note that the signal generated by this function needs further post-processing (to adjust its domain and range)
    before it represents a replica PRN signal.

    Ref: IS-GPS-200L §3.3.2.3: C/A-Code Generation
    """
    seq_bit_count = 10
    # PT: I'm out of my depth here, but it appears as though the scipy implementation needs to be passed the 'companion
    # set' of taps to produce the correct output sequence.
    #
    # If I'm understanding correctly, the GPS documentation specifies the taps in 'Galois generator' form, while the
    # scipy implementation needs to be provided the taps in 'Fibonacci generator' form.
    # Further reading: https://web.archive.org/web/20181001062252/http://www.newwaveinstruments.com/resources/articles/m_sequence_linear_feedback_shift_register_lfsr.htm
    #
    # Another way of understanding this which may also be correct: the GPS documentation vs. software libraries simply
    # describe the shift register in different orders from each other.
    #
    # (Terms 1 and X^n can be omitted as they're implicit.
    # X^n can be omitted because it'll be evaluated as 2^(x-x), which is zero anyway.)
    #
    # G1 = X^10 + X^3 + 1
    g1 = max_len_seq(seq_bit_count, taps=[seq_bit_count - 3])[0]
    # G2 = X^10 + X^9 + X^8 + X^6 + X^3 + X^2 + 1
    g2 = max_len_seq(seq_bit_count, taps=[
        seq_bit_count - 9,
        seq_bit_count - 8,
        seq_bit_count - 6,
        seq_bit_count - 3,
        seq_bit_count - 2,
        ])[0]
    return np.bitwise_xor(
        g1,
        np.roll(g2, delay_ms)
    )

    def PRN(sv):
        """Build the CA code (PRN) for a given satellite ID
        :param int sv: satellite code (1-32)
        :returns list: ca code for chosen satellite
        """


def shift(register, feedback, output):
    """GPS Shift Register
    :param list feedback: which positions to use as feedback (1 indexed)
    :param list output: which positions are output (1 indexed)
    :returns output of shift register:
    """
    # calculate output
    out = [register[i-1] for i in output]
    if len(out) > 1:
        out = sum(out) % 2
    else:
        out = out[0]

    # modulo 2 add feedback
    fb = sum([register[i-1] for i in feedback]) % 2

    # shift to the right
    for i in reversed(range(len(register[1:]))):
        register[i+1] = register[i]

    # put feedback in position 1
    register[0] = fb
    return out

def _generate_ca_code_with_taps(taps: list[int]) -> np.ndarray:
    # init registers
    G1 = [1 for _ in range(10)]
    G2 = [1 for _ in range(10)]

    ca = []
    # create sequence
    for _ in range(1023):
        g1 = shift(G1, [3,10], [10])
        g2 = shift(G2, [2,3,6,8,9,10], taps)

        # modulo 2 add and append to the code
        ca.append((g1 + g2) % 2)

    # return C/A code!
    return np.array(ca)


def generate_replica_prn_signals() -> dict[GpsSatelliteId, GpsReplicaPrnSignal]:
    # Ref: https://www.gps.gov/technical/icwg/IS-GPS-200L.pdf
    # Table 3-Ia. Code Phase Assignments
    # "The G2i sequence is a G2 sequence selectively delayed by pre-assigned number of chips, thereby
    # generating a set of different C/A-codes."
    # "The PRN C/A-code for SV ID number i is a Gold code, Gi(t), of 1 millisecond in length at a chipping
    # rate of 1023 kbps."
    # In other words, the C/A code for each satellite is a time-shifted version of the same signal, and the
    # delay is expressed in terms of a number of chips (each of which occupies 1ms).
    # PT: The above comment is wrong, the *total 1023-chip PRN* is transmitted every 1ms!
    satellite_id_to_g2_sequence_tap_configuration = {
        GpsSatelliteId(1): G2SequenceTapsConfiguration([2, 6]),
        GpsSatelliteId(2): G2SequenceTapsConfiguration([3, 7]),
        GpsSatelliteId(3): G2SequenceTapsConfiguration([4, 8]),
        GpsSatelliteId(4): G2SequenceTapsConfiguration([5, 9]),
        GpsSatelliteId(5): G2SequenceTapsConfiguration([1, 9]),
        GpsSatelliteId(6): G2SequenceTapsConfiguration([2, 10]),
        GpsSatelliteId(7): G2SequenceTapsConfiguration([1, 8]),
        GpsSatelliteId(8): G2SequenceTapsConfiguration([2, 9]),
        GpsSatelliteId(9): G2SequenceTapsConfiguration([3, 10]),
        GpsSatelliteId(10): G2SequenceTapsConfiguration([2, 3]),
        GpsSatelliteId(11): G2SequenceTapsConfiguration([3, 4]),
        GpsSatelliteId(12): G2SequenceTapsConfiguration([5, 6]),
        GpsSatelliteId(13): G2SequenceTapsConfiguration([6, 7]),
        GpsSatelliteId(14): G2SequenceTapsConfiguration([7, 8]),
        GpsSatelliteId(15): G2SequenceTapsConfiguration([8, 9]),
        GpsSatelliteId(16): G2SequenceTapsConfiguration([9, 10]),
        GpsSatelliteId(17): G2SequenceTapsConfiguration([1, 4]),
        GpsSatelliteId(18): G2SequenceTapsConfiguration([2, 5]),
        GpsSatelliteId(19): G2SequenceTapsConfiguration([3, 6]),
        GpsSatelliteId(20): G2SequenceTapsConfiguration([4, 7]),
        GpsSatelliteId(21): G2SequenceTapsConfiguration([5, 8]),
        GpsSatelliteId(22): G2SequenceTapsConfiguration([6, 9]),
        GpsSatelliteId(23): G2SequenceTapsConfiguration([1, 3]),
        GpsSatelliteId(24): G2SequenceTapsConfiguration([4, 6]),
        GpsSatelliteId(25): G2SequenceTapsConfiguration([5, 7]),
        GpsSatelliteId(26): G2SequenceTapsConfiguration([6, 8]),
        GpsSatelliteId(27): G2SequenceTapsConfiguration([7, 9]),
        GpsSatelliteId(28): G2SequenceTapsConfiguration([8, 10]),
        GpsSatelliteId(29): G2SequenceTapsConfiguration([1, 6]),
        GpsSatelliteId(30): G2SequenceTapsConfiguration([2, 7]),
        GpsSatelliteId(31): G2SequenceTapsConfiguration([3, 8]),
        GpsSatelliteId(32): G2SequenceTapsConfiguration([4, 9]),
    }

    # Generate each pure PRN signal.
    # Then, translate and scale each signal to match the representation used in BPSK.
    # In particular, the domain of the generated signals start out at [0 to 1].
    # Antenna data will instead vary from [-1 to 1].
    # Note each signal has exactly 1023 data points (which is the correct/exact length of the G2 code).
    output = {
        sat_id: (
            GpsReplicaPrnSignal(
                _generate_ca_code_with_taps(prn_tap_configs.taps)
            )
        )
        for sat_id, prn_tap_configs in satellite_id_to_g2_sequence_tap_configuration.items()
    }

    # Immediately verify that the PRNs were generated correctly
    expected_prn_starting_markers = {
        GpsSatelliteId(1): 1440,
        GpsSatelliteId(2): 1620,
        GpsSatelliteId(3): 1710,
        GpsSatelliteId(4): 1744,
        GpsSatelliteId(5): 1133,
        GpsSatelliteId(6): 1455,
        GpsSatelliteId(7): 1131,
        GpsSatelliteId(8): 1454,
        GpsSatelliteId(9): 1626,
        GpsSatelliteId(10): 1504,
        GpsSatelliteId(11): 1642,
        GpsSatelliteId(12): 1750,
        GpsSatelliteId(13): 1764,
        GpsSatelliteId(14): 1772,
        GpsSatelliteId(15): 1775,
        GpsSatelliteId(16): 1776,
        GpsSatelliteId(17): 1156,
        GpsSatelliteId(18): 1467,
        GpsSatelliteId(19): 1633,
        GpsSatelliteId(20): 1715,
        GpsSatelliteId(21): 1746,
        GpsSatelliteId(22): 1763,
        GpsSatelliteId(23): 1063,
        GpsSatelliteId(24): 1706,
        GpsSatelliteId(25): 1743,
        GpsSatelliteId(26): 1761,
        GpsSatelliteId(27): 1770,
        GpsSatelliteId(28): 1774,
        GpsSatelliteId(29): 1127,
        GpsSatelliteId(30): 1453,
        GpsSatelliteId(31): 1625,
        GpsSatelliteId(32): 1712,
    }
    for satellite_id, expected_prn_start in expected_prn_starting_markers.items():
        #print(f'Testing PRN for SV {satellite_id}...')
        prn = output[satellite_id].inner
        expected_prn_start_octal_digits = str(expected_prn_start)
        #print(expected_prn_start_octal_digits)
        # The PRN needs to always start high
        if expected_prn_start_octal_digits[0] != '1':
            raise ValueError(f'Test vector PRN is always expected to begin with 1')
        if prn[0] != 1:
            raise ValueError(f'Generated PRNs always need to start with 1')

        # Skip the starting 1
        expected_prn_start_octal_digits = expected_prn_start_octal_digits[1:]
        #print(prn)
        prn = prn[1:]

        for digit_idx, expected_prn_octal_digit in enumerate(expected_prn_start_octal_digits):
            actual_prn_bits_start_idx = digit_idx * 3
            actual_prn_octal_digit = int(''.join([str(bit) for bit in prn[actual_prn_bits_start_idx:actual_prn_bits_start_idx+3]]), 2)
            if actual_prn_octal_digit != int(expected_prn_octal_digit):
                raise ValueError(f'SV {satellite_id.id}: PRN digit {actual_prn_octal_digit} didn\'t match expected digit {expected_prn_octal_digit}')

    return output
