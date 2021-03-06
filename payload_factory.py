from hashlib import sha256
from txtenna_segment import TxSegment
from z85 import is_z85, decode, encode
from utilities import hash256

# from bitcoin.core import CTransaction

SMS_SEGMENT_0_LEN = 40
SMS_SEGMENT_1_LEN = 120

GOTENNA_SEGMENT_0_LEN = 100
GOTENNA_SEGMENT_1_LEN = 180


class IncompletePayloadSegmentsError(Exception):
    def __init__(self, message, index):
        super().__init__(f"{message} at index {index}")
        self.missing_index = index


def raise_error_if_missing_segments(index, segment, length):
    if index != segment.sequence_num:
        raise IncompletePayloadSegmentsError("Missing segment", index)
    elif segment.sequence_num == 0 and segment.segment_count != length:
        raise IncompletePayloadSegmentsError("Segments length does not match anticipated count in head", index)


def get_tx_hash(tx_as_bytes):
    return sha256(sha256(tx_as_bytes).digest()).digest()[::-1]


class PayloadFactory:

    @staticmethod
    def from_json(json_segments):
        return PayloadFactory.from_segments([TxSegment.deserialize_from_json(json_segment)
                                             for json_segment in json_segments])

    @staticmethod
    def from_segments(segments):
        tx = ""
        tx_hash = ""
        segments_length = len(segments)

        for i, segment in enumerate(sorted(segments, key=lambda s: s.sequence_num)):
            raise_error_if_missing_segments(i, segment, segments_length)
            if segment.sequence_num == 0:
                if is_z85(segment.tx_hash):
                    tx_hash = decode(segment.tx_hash)
                else:
                    tx_hash = bytes.fromhex(segment.tx_hash)
            tx += segment.tx_data

        decoded_tx = decode(tx) if is_z85(tx) else bytes.fromhex(tx)
        if get_tx_hash(decoded_tx) != tx_hash:
            raise ValueError("Transaction payload does not validate against transaction hash")

        return decoded_tx

    @staticmethod
    def to_segments(tx: bytes, payload_id: str, is_gotenna: bool = True, use_z85: bool = True,
                    is_testnet: bool = False):

        def get_segment_lengths():
            if is_gotenna:
                segment_0_length = GOTENNA_SEGMENT_0_LEN
                segment_m_length = GOTENNA_SEGMENT_1_LEN
            else:
                segment_0_length = SMS_SEGMENT_0_LEN
                segment_m_length = SMS_SEGMENT_1_LEN

            if use_z85:
                segment_0_length += 24

            return (segment_0_length, segment_m_length)

        def get_tx_raw_data():
            if use_z85:
                tx_encoded = encode(tx)
                hash = encode(bytes.fromhex(hash256(tx).hex()))
            else:
                tx_encoded = tx.hex()
                hash = hash256(tx).hex()
            return tx_encoded, hash

        segment_0_length, segment_m_length = get_segment_lengths()
        tx_raw, tx_hash = get_tx_raw_data()

        segments = []
        raw_tx_length = len(tx_raw)
        segment_count = 1

        if raw_tx_length > segment_0_length:
            raw_tx_length -= segment_0_length
            quotient, remainder = divmod(raw_tx_length, segment_m_length)
            segment_count += quotient + int(remainder > 0)
        else:
            segment_0_length = raw_tx_length

        for i in range(0, segment_count):
            if i == 0:
                tx_data = tx_raw[0:segment_0_length]
                seg_0 = TxSegment(payload_id, tx_data, 0, tx_hash=tx_hash, testnet=is_testnet,
                                  segment_count=segment_count)
                segments.append(seg_0)
            else:
                tx_raw_index = segment_0_length + (i - 1) * segment_m_length

                if i < segment_count - 1:
                    tx_data = tx_raw[tx_raw_index:tx_raw_index + segment_m_length]
                else:
                    tx_data = tx_raw[tx_raw_index:]

                seg = TxSegment(payload_id, tx_data, i)
                segments.append(seg)

        return segments

    @staticmethod
    def to_json(tx, payload_id, is_gotenna=True, use_z85=True, is_testnet=False):
        return [segment.serialize_to_json() for segment in
                PayloadFactory.to_segments(tx, payload_id, is_gotenna=is_gotenna, use_z85=use_z85,
                                           is_testnet=is_testnet)]
