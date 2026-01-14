"""
Contract Generator for Louisiana Land Wholesaling

Generates legally-compliant documents for real estate transactions:
- Purchase Agreement (Buyer-Seller contract)
- Assignment Contract (Wholesaler assigns to end buyer)
- PDF generation with auto-filled data
- Digital signature placeholders
- Export to file system
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.logging_config import get_logger
from core.utils import utcnow

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Get project root for contracts directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
TEMPLATES_DIR = CONTRACTS_DIR / "templates"
GENERATED_DIR = CONTRACTS_DIR / "generated"


@dataclass
class SellerInfo:
    """Seller information for contracts."""
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: Optional[str] = None
    email: Optional[str] = None


@dataclass
class BuyerInfo:
    """Buyer information for contracts."""
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone: Optional[str] = None
    email: Optional[str] = None
    entity_type: str = "individual"  # individual, llc, corporation


@dataclass
class PropertyInfo:
    """Property information for contracts."""
    address: str
    city: str
    state: str
    zip_code: str
    parish_county: str
    parcel_number: str
    lot_size_acres: float
    legal_description: Optional[str] = None
    zoning: Optional[str] = None


@dataclass
class DealTerms:
    """Financial terms of the deal."""
    purchase_price: float
    earnest_money: float
    closing_date: datetime
    inspection_days: int = 14
    financing_contingency: bool = False
    financing_days: int = 0
    title_company: Optional[str] = None
    title_company_address: Optional[str] = None
    additional_terms: List[str] = field(default_factory=list)


@dataclass
class AssignmentTerms:
    """Terms for assignment contract."""
    original_purchase_price: float
    assignment_fee: float
    total_price: float  # original + assignment fee
    assignment_date: datetime
    end_buyer_deposit: float = 0.0


@dataclass
class ContractDocument:
    """Generated contract document."""
    contract_type: str  # purchase_agreement, assignment
    lead_id: int
    filename: str
    filepath: str
    generated_at: datetime
    content_text: str
    content_html: str
    pdf_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "lead_id": self.lead_id,
            "filename": self.filename,
            "filepath": self.filepath,
            "generated_at": self.generated_at.isoformat(),
            "pdf_path": self.pdf_path,
        }


class ContractGenerator:
    """
    Generate real estate contracts for Louisiana land wholesaling.
    
    Supported contract types:
    - Purchase Agreement: Contract between seller and wholesaler
    - Assignment Contract: Contract assigning purchase rights to end buyer
    """
    
    # Louisiana-specific legal requirements
    STATE = "Louisiana"
    STATE_CODE = "LA"

    def __init__(self):
        """Initialize the contract generator."""
        # Ensure directories exist
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    def generate_purchase_agreement(
        self,
        lead_id: int,
        seller: SellerInfo,
        buyer: BuyerInfo,
        property_info: PropertyInfo,
        terms: DealTerms,
    ) -> ContractDocument:
        """
        Generate a Purchase Agreement contract.
        
        Args:
            lead_id: Associated lead ID.
            seller: Seller information.
            buyer: Buyer (wholesaler) information.
            property_info: Property details.
            terms: Deal terms.
            
        Returns:
            ContractDocument with generated content.
        """
        # Generate contract content
        content_text = self._generate_purchase_agreement_text(
            seller, buyer, property_info, terms
        )
        
        content_html = self._generate_purchase_agreement_html(
            seller, buyer, property_info, terms
        )
        
        # Generate filename
        timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"purchase_agreement_{lead_id}_{timestamp}"
        
        # Save text version
        text_path = GENERATED_DIR / f"{filename}.txt"
        text_path.write_text(content_text, encoding="utf-8")
        
        # Save HTML version
        html_path = GENERATED_DIR / f"{filename}.html"
        html_path.write_text(content_html, encoding="utf-8")
        
        # Generate PDF if possible
        pdf_path = self._generate_pdf(content_html, filename)
        
        LOGGER.info(f"Generated purchase agreement for lead {lead_id}: {filename}")
        
        return ContractDocument(
            contract_type="purchase_agreement",
            lead_id=lead_id,
            filename=filename,
            filepath=str(text_path),
            generated_at=utcnow(),
            content_text=content_text,
            content_html=content_html,
            pdf_path=pdf_path,
        )

    def generate_assignment_contract(
        self,
        lead_id: int,
        original_seller: SellerInfo,
        assignor: BuyerInfo,  # The wholesaler
        assignee: BuyerInfo,  # The end buyer
        property_info: PropertyInfo,
        assignment_terms: AssignmentTerms,
        original_contract_date: datetime,
    ) -> ContractDocument:
        """
        Generate an Assignment Contract.
        
        Args:
            lead_id: Associated lead ID.
            original_seller: Original property seller.
            assignor: Wholesaler assigning the contract.
            assignee: End buyer receiving assignment.
            property_info: Property details.
            assignment_terms: Assignment financial terms.
            original_contract_date: Date of original purchase agreement.
            
        Returns:
            ContractDocument with generated content.
        """
        content_text = self._generate_assignment_text(
            original_seller, assignor, assignee, property_info,
            assignment_terms, original_contract_date
        )
        
        content_html = self._generate_assignment_html(
            original_seller, assignor, assignee, property_info,
            assignment_terms, original_contract_date
        )
        
        # Generate filename
        timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"assignment_contract_{lead_id}_{timestamp}"
        
        # Save files
        text_path = GENERATED_DIR / f"{filename}.txt"
        text_path.write_text(content_text, encoding="utf-8")
        
        html_path = GENERATED_DIR / f"{filename}.html"
        html_path.write_text(content_html, encoding="utf-8")
        
        pdf_path = self._generate_pdf(content_html, filename)
        
        LOGGER.info(f"Generated assignment contract for lead {lead_id}: {filename}")
        
        return ContractDocument(
            contract_type="assignment",
            lead_id=lead_id,
            filename=filename,
            filepath=str(text_path),
            generated_at=utcnow(),
            content_text=content_text,
            content_html=content_html,
            pdf_path=pdf_path,
        )

    def _generate_purchase_agreement_text(
        self,
        seller: SellerInfo,
        buyer: BuyerInfo,
        property_info: PropertyInfo,
        terms: DealTerms,
    ) -> str:
        """Generate purchase agreement in plain text format."""
        closing_date_str = terms.closing_date.strftime("%B %d, %Y")
        today_str = utcnow().strftime("%B %d, %Y")
        inspection_deadline = (utcnow() + timedelta(days=terms.inspection_days)).strftime("%B %d, %Y")
        
        legal_desc = property_info.legal_description or f"Parcel #{property_info.parcel_number} as recorded in the official records of {property_info.parish_county} Parish, Louisiana"
        
        contract = f"""
================================================================================
                    LOUISIANA REAL ESTATE PURCHASE AGREEMENT
                           (Vacant Land / Unimproved Property)
================================================================================

CONTRACT DATE: {today_str}

================================================================================
                              PARTIES TO THE AGREEMENT
================================================================================

SELLER:
    Name: {seller.name}
    Address: {seller.address}
    City/State/ZIP: {seller.city}, {seller.state} {seller.zip_code}
    Phone: {seller.phone or "N/A"}
    Email: {seller.email or "N/A"}

BUYER:
    Name: {buyer.name}
    Address: {buyer.address}
    City/State/ZIP: {buyer.city}, {buyer.state} {buyer.zip_code}
    Phone: {buyer.phone or "N/A"}
    Email: {buyer.email or "N/A"}

================================================================================
                              PROPERTY DESCRIPTION
================================================================================

PROPERTY ADDRESS:
    {property_info.address}
    {property_info.city}, {property_info.state} {property_info.zip_code}

PARISH: {property_info.parish_county}

PARCEL/ASSESSOR NUMBER: {property_info.parcel_number}

LOT SIZE: Approximately {property_info.lot_size_acres:.2f} acres

LEGAL DESCRIPTION:
    {legal_desc}

ZONING: {property_info.zoning or "To be verified by Buyer"}

================================================================================
                              PURCHASE TERMS
================================================================================

1. PURCHASE PRICE: ${terms.purchase_price:,.2f} (US Dollars)

2. EARNEST MONEY DEPOSIT: ${terms.earnest_money:,.2f}
   To be deposited within three (3) business days of execution of this Agreement
   with:
   {terms.title_company or "[Title Company to be designated]"}
   {terms.title_company_address or ""}

3. BALANCE DUE AT CLOSING: ${(terms.purchase_price - terms.earnest_money):,.2f}
   To be paid in certified funds at closing.

4. CLOSING DATE: On or before {closing_date_str}

================================================================================
                              CONTINGENCIES
================================================================================

5. INSPECTION CONTINGENCY:
   Buyer shall have until {inspection_deadline} ({terms.inspection_days} days from 
   contract execution) to conduct any inspections, surveys, environmental 
   assessments, or other due diligence at Buyer's expense. Buyer may terminate 
   this Agreement for any reason during the inspection period and receive a 
   full refund of earnest money.

6. TITLE CONTINGENCY:
   This Agreement is contingent upon Seller providing marketable title, free 
   and clear of all liens, encumbrances, and defects, except for current year 
   property taxes and recorded easements of record that do not materially 
   affect the use of the Property.

7. ASSIGNMENT:
   Buyer may assign this Agreement and all rights hereunder to any third party 
   without Seller's consent. Seller agrees to cooperate with any such assignment.

================================================================================
                              SELLER REPRESENTATIONS
================================================================================

8. Seller represents and warrants:
   a) Seller is the legal owner of the Property with full authority to sell
   b) There are no undisclosed liens or encumbrances on the Property
   c) There are no pending legal actions affecting the Property
   d) All property taxes are current through the prior year
   e) There are no known environmental issues or hazardous materials
   f) The Property is not subject to any lease or rental agreement

================================================================================
                              ADDITIONAL TERMS
================================================================================

9. CLOSING COSTS:
   Seller shall pay: Deed preparation, Seller's portion of prorated taxes,
   any mortgage payoffs
   
   Buyer shall pay: Title insurance, recording fees, Buyer's portion of
   prorated taxes, title search

10. POSSESSION: Seller shall deliver possession at closing.

11. RISK OF LOSS: Risk of loss shall remain with Seller until closing.

{"12. ADDITIONAL PROVISIONS:" if terms.additional_terms else ""}
{chr(10).join(f"    - {term}" for term in terms.additional_terms) if terms.additional_terms else ""}

================================================================================
                              SIGNATURES
================================================================================

This Agreement shall be binding upon the heirs, successors, and assigns of 
both parties.

SELLER:

Signature: ___________________________________  Date: ____________

Printed Name: {seller.name}


BUYER:

Signature: ___________________________________  Date: ____________

Printed Name: {buyer.name}


================================================================================
                              ACKNOWLEDGMENT
================================================================================

This document was prepared for informational purposes. Both parties are 
advised to have this Agreement reviewed by a licensed Louisiana attorney 
prior to execution.

================================================================================
"""
        return contract.strip()

    def _generate_purchase_agreement_html(
        self,
        seller: SellerInfo,
        buyer: BuyerInfo,
        property_info: PropertyInfo,
        terms: DealTerms,
    ) -> str:
        """Generate purchase agreement in HTML format."""
        text_content = self._generate_purchase_agreement_text(
            seller, buyer, property_info, terms
        )
        
        # Convert to HTML with basic styling
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Purchase Agreement - {property_info.parcel_number}</title>
    <style>
        body {{
            font-family: 'Times New Roman', Times, serif;
            font-size: 12pt;
            line-height: 1.5;
            max-width: 8.5in;
            margin: 0.5in auto;
            padding: 0.5in;
        }}
        h1 {{
            text-align: center;
            font-size: 16pt;
            border-bottom: 2px solid #000;
            padding-bottom: 10px;
        }}
        h2 {{
            font-size: 14pt;
            margin-top: 20px;
            border-bottom: 1px solid #000;
        }}
        .section {{
            margin-bottom: 20px;
        }}
        .signature-block {{
            margin-top: 40px;
        }}
        .signature-line {{
            border-bottom: 1px solid #000;
            width: 300px;
            display: inline-block;
            margin-right: 20px;
        }}
        pre {{
            white-space: pre-wrap;
            font-family: inherit;
        }}
    </style>
</head>
<body>
    <pre>{text_content}</pre>
</body>
</html>
"""
        return html

    def _generate_assignment_text(
        self,
        original_seller: SellerInfo,
        assignor: BuyerInfo,
        assignee: BuyerInfo,
        property_info: PropertyInfo,
        terms: AssignmentTerms,
        original_contract_date: datetime,
    ) -> str:
        """Generate assignment contract in plain text format."""
        today_str = utcnow().strftime("%B %d, %Y")
        original_date_str = original_contract_date.strftime("%B %d, %Y")
        assignment_date_str = terms.assignment_date.strftime("%B %d, %Y")
        
        contract = f"""
================================================================================
                    ASSIGNMENT OF REAL ESTATE PURCHASE AGREEMENT
                                    STATE OF LOUISIANA
================================================================================

ASSIGNMENT DATE: {today_str}

================================================================================
                              PARTIES TO THE ASSIGNMENT
================================================================================

ASSIGNOR (Original Buyer):
    Name: {assignor.name}
    Address: {assignor.address}
    City/State/ZIP: {assignor.city}, {assignor.state} {assignor.zip_code}
    Phone: {assignor.phone or "N/A"}

ASSIGNEE (New Buyer):
    Name: {assignee.name}
    Address: {assignee.address}
    City/State/ZIP: {assignee.city}, {assignee.state} {assignee.zip_code}
    Phone: {assignee.phone or "N/A"}

================================================================================
                              RECITALS
================================================================================

WHEREAS, Assignor entered into a Real Estate Purchase Agreement dated 
{original_date_str} ("Original Agreement") with {original_seller.name} 
("Seller") for the purchase of the following described property:

PROPERTY:
    Address: {property_info.address}
    {property_info.city}, {property_info.state} {property_info.zip_code}
    Parish: {property_info.parish_county}
    Parcel Number: {property_info.parcel_number}
    Lot Size: Approximately {property_info.lot_size_acres:.2f} acres

WHEREAS, the Original Agreement provides for an original purchase price of 
${terms.original_purchase_price:,.2f}; and

WHEREAS, the Original Agreement permits assignment; and

WHEREAS, Assignor desires to assign all right, title, and interest in the 
Original Agreement to Assignee, and Assignee desires to accept such assignment.

================================================================================
                              ASSIGNMENT TERMS
================================================================================

NOW, THEREFORE, in consideration of the mutual covenants herein and other good 
and valuable consideration, the receipt and sufficiency of which are hereby 
acknowledged, the parties agree as follows:

1. ASSIGNMENT OF RIGHTS
   Assignor hereby assigns, transfers, and conveys to Assignee all of Assignor's
   right, title, and interest in and to the Original Agreement, including all
   rights to purchase the Property under the terms of the Original Agreement.

2. ASSIGNMENT FEE
   In consideration for this assignment, Assignee shall pay to Assignor an
   assignment fee of:
   
   ASSIGNMENT FEE: ${terms.assignment_fee:,.2f}
   
   This fee shall be paid as follows:
   - Deposit upon execution of this Assignment: ${terms.end_buyer_deposit:,.2f}
   - Balance due at closing: ${(terms.assignment_fee - terms.end_buyer_deposit):,.2f}

3. TOTAL AMOUNT DUE FROM ASSIGNEE AT CLOSING
   Original Purchase Price: ${terms.original_purchase_price:,.2f}
   Plus Assignment Fee: ${terms.assignment_fee:,.2f}
   TOTAL: ${terms.total_price:,.2f}

4. CLOSING
   The closing shall occur on {assignment_date_str} or as otherwise provided
   in the Original Agreement.

5. ASSUMPTION OF OBLIGATIONS
   Assignee hereby assumes all obligations, duties, and liabilities of Assignor
   under the Original Agreement.

6. REPRESENTATIONS AND WARRANTIES
   
   Assignor represents and warrants that:
   a) The Original Agreement is in full force and effect
   b) Assignor has not defaulted under the Original Agreement
   c) Assignor has full authority to make this assignment
   d) The Original Agreement permits assignment
   
   Assignee represents and warrants that:
   a) Assignee has reviewed the Original Agreement
   b) Assignee accepts all terms of the Original Agreement
   c) Assignee has the financial ability to close the transaction

7. INDEMNIFICATION
   Assignee shall indemnify and hold harmless Assignor from any claims arising
   from Assignee's failure to perform under the Original Agreement after the
   date of this Assignment.

8. GOVERNING LAW
   This Assignment shall be governed by the laws of the State of Louisiana.

================================================================================
                              SIGNATURES
================================================================================

IN WITNESS WHEREOF, the parties have executed this Assignment as of the date
first written above.

ASSIGNOR:

Signature: ___________________________________  Date: ____________

Printed Name: {assignor.name}


ASSIGNEE:

Signature: ___________________________________  Date: ____________

Printed Name: {assignee.name}


================================================================================
                              ACKNOWLEDGMENT
================================================================================

STATE OF LOUISIANA
PARISH OF ____________________

Before me, the undersigned Notary Public, personally appeared:

_________________________ (Assignor) and _________________________ (Assignee),

known to me to be the persons whose names are subscribed to the foregoing
instrument, and acknowledged that they executed the same for the purposes
therein expressed.

IN WITNESS WHEREOF, I have hereunto set my hand and official seal this
_____ day of _________________, 20_____.


                              ___________________________________
                              Notary Public
                              My Commission Expires: ______________

================================================================================
                              DISCLAIMER
================================================================================

This document was prepared for informational purposes. All parties are advised
to have this Assignment reviewed by a licensed Louisiana attorney prior to
execution. This Assignment does not constitute legal advice.

================================================================================
"""
        return contract.strip()

    def _generate_assignment_html(
        self,
        original_seller: SellerInfo,
        assignor: BuyerInfo,
        assignee: BuyerInfo,
        property_info: PropertyInfo,
        terms: AssignmentTerms,
        original_contract_date: datetime,
    ) -> str:
        """Generate assignment contract in HTML format."""
        text_content = self._generate_assignment_text(
            original_seller, assignor, assignee, property_info,
            terms, original_contract_date
        )
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Assignment Contract - {property_info.parcel_number}</title>
    <style>
        body {{
            font-family: 'Times New Roman', Times, serif;
            font-size: 12pt;
            line-height: 1.5;
            max-width: 8.5in;
            margin: 0.5in auto;
            padding: 0.5in;
        }}
        h1 {{
            text-align: center;
            font-size: 16pt;
            border-bottom: 2px solid #000;
            padding-bottom: 10px;
        }}
        pre {{
            white-space: pre-wrap;
            font-family: inherit;
        }}
    </style>
</head>
<body>
    <pre>{text_content}</pre>
</body>
</html>
"""
        return html

    def _generate_pdf(self, html_content: str, filename: str) -> Optional[str]:
        """
        Generate PDF from HTML content.
        
        Requires weasyprint or similar library to be installed.
        Returns None if PDF generation is not available.
        """
        try:
            from weasyprint import HTML
            
            pdf_path = GENERATED_DIR / f"{filename}.pdf"
            HTML(string=html_content).write_pdf(str(pdf_path))
            
            LOGGER.info(f"Generated PDF: {pdf_path}")
            return str(pdf_path)
            
        except ImportError:
            LOGGER.warning("weasyprint not installed - PDF generation skipped")
            return None
        except Exception as e:
            LOGGER.error(f"PDF generation failed: {e}")
            return None

    def get_contract_templates(self) -> Dict[str, str]:
        """Get available contract templates."""
        return {
            "purchase_agreement": "Louisiana Real Estate Purchase Agreement",
            "assignment": "Assignment of Purchase Agreement",
        }

    def list_generated_contracts(self, lead_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List generated contracts, optionally filtered by lead ID.
        
        Returns list of contract metadata.
        """
        contracts = []
        
        for filepath in GENERATED_DIR.glob("*.txt"):
            parts = filepath.stem.split("_")
            
            if len(parts) >= 3:
                contract_type = parts[0]
                contract_lead_id = int(parts[-2]) if parts[-2].isdigit() else None
                
                if lead_id and contract_lead_id != lead_id:
                    continue
                
                contracts.append({
                    "filename": filepath.name,
                    "contract_type": contract_type,
                    "lead_id": contract_lead_id,
                    "created_at": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                    "filepath": str(filepath),
                    "has_pdf": (filepath.parent / f"{filepath.stem}.pdf").exists(),
                })
        
        return sorted(contracts, key=lambda x: x["created_at"], reverse=True)


def get_contract_generator() -> ContractGenerator:
    """Get a ContractGenerator instance."""
    return ContractGenerator()


__all__ = [
    "ContractGenerator",
    "ContractDocument",
    "SellerInfo",
    "BuyerInfo",
    "PropertyInfo",
    "DealTerms",
    "AssignmentTerms",
    "get_contract_generator",
]

