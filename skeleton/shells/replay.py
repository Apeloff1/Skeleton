"""Evidence replay and verification without process re-execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from skeleton.shells.attestations import Attestation,HMACAttestor
from skeleton.shells.receipts import ChainedReceipt,ExecutionReceipt,ReceiptChain


class ReplayStatus(str,Enum):
    VERIFIED="verified"
    INVALID_CHAIN="invalid_chain"
    INVALID_ATTESTATION="invalid_attestation"
    MISSING_ATTESTATION="missing_attestation"


@dataclass(frozen=True)
class ReplayItem:
    sequence:int
    receipt_id:str
    status:ReplayStatus
    command:str
    correlation_id:str

    def to_dict(self)->dict[str,object]:
        return {
            "sequence":self.sequence,"receipt_id":self.receipt_id,
            "status":self.status.value,"command":self.command,
            "correlation_id":self.correlation_id,
        }


@dataclass(frozen=True)
class ReplayReport:
    items:tuple[ReplayItem,...]
    chain_valid:bool

    @property
    def valid(self)->bool:
        return self.chain_valid and all(item.status is ReplayStatus.VERIFIED for item in self.items)

    def to_dict(self)->dict[str,object]:
        return {"valid":self.valid,"chain_valid":self.chain_valid,"items":[item.to_dict() for item in self.items]}


class EvidenceReplay:
    """Verify receipt history. Never executes a command."""

    def verify_chain(self,chain:ReceiptChain)->ReplayReport:
        valid=chain.verify()
        items=tuple(
            ReplayItem(
                item.sequence,item.receipt.receipt_id,
                ReplayStatus.VERIFIED if valid else ReplayStatus.INVALID_CHAIN,
                item.receipt.command,item.receipt.correlation_id,
            )
            for item in chain.snapshot()
        )
        return ReplayReport(items,valid)

    def verify_attested(
        self,
        receipts:Iterable[ExecutionReceipt],
        attestations:dict[str,Attestation],
        attestor:HMACAttestor,
    )->ReplayReport:
        items=[]
        for sequence,receipt in enumerate(receipts,start=1):
            attestation=attestations.get(receipt.receipt_id)
            if attestation is None:
                status=ReplayStatus.MISSING_ATTESTATION
            elif attestor.verify_receipt(receipt,attestation):
                status=ReplayStatus.VERIFIED
            else:
                status=ReplayStatus.INVALID_ATTESTATION
            items.append(ReplayItem(sequence,receipt.receipt_id,status,receipt.command,receipt.correlation_id))
        return ReplayReport(tuple(items),True)
