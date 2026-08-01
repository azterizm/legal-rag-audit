from typing import List, Dict, Any, Set

class CitationEvaluator:
    def __init__(self):
        pass

    def evaluate(self, returned_citations: List[Any], valid_document_ids: Set[str]) -> Dict[str, Any]:
        """
        Verifies that citations returned in the API match the valid document IDs we uploaded.
        """
        phantom_citations = []
        for cite in returned_citations:
            # Try to extract an ID from the citation
            cite_id = cite.get('id') if isinstance(cite, dict) else str(cite)
            
            if cite_id not in valid_document_ids:
                phantom_citations.append(cite_id)
                
        status = "FAIL" if phantom_citations else "PASS"
        
        return {
            "status": status,
            "phantom_citations": len(phantom_citations),
            "total_citations": len(returned_citations),
            "details": {
                "invalid_citations": phantom_citations
            } if phantom_citations else {}
        }
