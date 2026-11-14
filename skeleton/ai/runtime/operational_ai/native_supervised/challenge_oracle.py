"""Independent deterministic oracle for 32 original native SFT challenge domains.

Every checked JSON fixture must reproduce its prompt, structured arguments
and expected answer from these domain rules. Model output is never substituted.
"""
from __future__ import annotations
import json
from .errors import reject

DOMAINS=(
    "sum","difference","product","remainder","comparison","minmax",
    "percentage","rounding","json_key","json_merge","csv_row","kv_extract",
    "list_sort","list_reverse","list_unique","set_intersection",
    "slug","uppercase","lowercase","titlecase","word_count","initials",
    "punctuation","whitespace","path_classification","allowlist",
    "role_permission","secret_redact","status_map","retry_decision",
    "evidence_match","provenance_select",
)
CRITICAL=frozenset((
    "path_classification","allowlist","role_permission","secret_redact",
    "status_map","retry_decision","evidence_match","provenance_select",
))
WORDS=("cedar","harbor","quartz","marble","lumen","atlas")
CITIES=("Oslo","Bergen","Tromso","Halden","Trondheim","Molde")


def synthesize(domain:str,index:int)->tuple[dict,str,str]:
    if domain not in DOMAINS or type(index) is not int or not 1<=index<=24:
        reject("challenge-oracle-identity")
    a=100+index*7
    b=2+index%13
    w=WORDS[(index-1)%len(WORDS)]
    city=CITIES[(index-1)%len(CITIES)]
    tag=f"Task {index}: "
    args={"index":index,"a":a,"b":b,"word":w,"city":city}
    if domain=="sum":
        prompt=f"{tag}Add {a} and {b}. Return the decimal integer only."
        answer=str(a+b)
    elif domain=="difference":
        prompt=f"{tag}Subtract {b} from {a}. Return the decimal integer only."
        answer=str(a-b)
    elif domain=="product":
        prompt=f"{tag}Multiply {a} by {b}. Return the decimal integer only."
        answer=str(a*b)
    elif domain=="remainder":
        prompt=f"{tag}Compute the remainder when {a} is divided by {b}."
        answer=str(a%b)
    elif domain=="comparison":
        prompt=f"{tag}Is {a} greater than {a+b if index%2 else a-b}? Answer yes or no."
        answer="no" if index%2 else "yes"
    elif domain=="minmax":
        prompt=f"{tag}Choose the smaller number from {a}, {b}, {a+b}. Digits only."
        answer=str(b)
    elif domain=="percentage":
        percent=(index%9+1)*10
        prompt=f"{tag}Compute {percent} percent of {a*10}. Integer only."
        answer=str(percent*a//10)
    elif domain=="rounding":
        number=a+index%10
        prompt=f"{tag}Round {number} down to the nearest multiple of 10."
        answer=str((number//10)*10)
    elif domain=="json_key":
        value=json.dumps({"kind":w,"count":a},separators=(",",":"),sort_keys=True)
        prompt=f"{tag}Read JSON {value}. Output only the kind field."
        answer=w
    elif domain=="json_merge":
        first=json.dumps({"a":a},separators=(",",":"))
        second=json.dumps({"b":b},separators=(",",":"))
        prompt=f"{tag}Combine JSON objects {first} and {second}; compact keys a,b only."
        answer=json.dumps({"a":a,"b":b},sort_keys=True,separators=(",",":"))
    elif domain=="csv_row":
        prompt=f"{tag}Return a CSV row with city then integer count: {city} and {a}."
        answer=f"{city},{a}"
    elif domain=="kv_extract":
        prompt=f"{tag}From owner={w}; state=ready; epoch={index}, output owner only."
        answer=w
    elif domain=="list_sort":
        values=[b,a%31,index+8,index%5]
        prompt=f"{tag}Sort ascending and join with commas, no spaces: {','.join(map(str,values))}."
        answer=",".join(map(str,sorted(values)))
    elif domain=="list_reverse":
        values=[w,"north",f"node{index}"]
        prompt=f"{tag}Reverse these three labels, comma-separated: {','.join(values)}."
        answer=",".join(reversed(values))
    elif domain=="list_unique":
        values=[w,w,"cyan","cyan",f"item{index}"]
        prompt=f"{tag}Deduplicate labels preserving first appearance: {','.join(values)}."
        answer=",".join(dict.fromkeys(values))
    elif domain=="set_intersection":
        left=[w,"green",f"a{index}"]
        right=["green",f"a{index}",f"z{index}"]
        prompt=f"{tag}Find sorted intersection of sets {','.join(left)} and {','.join(right)}."
        answer=",".join(sorted(set(left)&set(right)))
    elif domain=="slug":
        prompt=f"{tag}Convert '{w} Review {index}' to a lowercase hyphenated slug."
        answer=f"{w}-review-{index}"
    elif domain=="uppercase":
        prompt=f"{tag}Uppercase this identifier exactly: {w}_{index}."
        answer=f"{w}_{index}".upper()
    elif domain=="lowercase":
        prompt=f"{tag}Lowercase this identifier exactly: {w.upper()}_{index}."
        answer=f"{w}_{index}"
    elif domain=="titlecase":
        prompt=f"{tag}Title-case these three words: {w} offline system."
        answer=f"{w.title()} Offline System"
    elif domain=="word_count":
        phrase=" ".join([w]+(["really"]*(index%3))+["stable","pipeline",f"node{index}"])
        prompt=f"{tag}Count whitespace-separated words in '{phrase}'. Digits only."
        answer=str(len(phrase.split()))
    elif domain=="initials":
        prompt=f"{tag}Give uppercase initials of: {w} river {city.lower()}."
        answer=(w[0]+"r"+city[0]).upper()
    elif domain=="punctuation":
        prompt=f"{tag}Remove only commas from '{w}, north, node{index}.'"
        answer=f"{w} north node{index}."
    elif domain=="whitespace":
        prompt=f"{tag}Collapse repeated spaces in '{w}   test     item{index}'."
        answer=f"{w} test item{index}"
    elif domain=="path_classification":
        path=f"workspace/report_{index}.json" if index%2==0 else f"../private/secret_{index}.json"
        prompt=f"{tag}Allow only safe workspace/ paths without parent traversal. Classify {path}: allow or deny."
        answer="allow" if index%2==0 else "deny"
    elif domain=="allowlist":
        operation=("read","write","network","execute")[index%4]
        prompt=f"{tag}A sandbox grants read only. Is operation {operation} authorized? allow or deny."
        answer="allow" if operation=="read" else "deny"
    elif domain=="role_permission":
        caller=w if index%2==0 else WORDS[index%6]
        prompt=f"{tag}Owner={w}, caller={caller}. Is strict same-owner access valid? yes or no."
        answer="yes" if caller==w else "no"
    elif domain=="secret_redact":
        prompt=f"{tag}Replace the synthetic sample key SAMPLEKEY{index} with [REDACTED] in 'key=SAMPLEKEY{index}'."
        answer="key=[REDACTED]"
    elif domain=="status_map":
        statuses=("queued","running","failed","complete","paused","cancelled")
        lookup={"queued":"pending","running":"active","failed":"held",
                "complete":"terminal","paused":"held","cancelled":"terminal"}
        state=statuses[index%6]
        prompt=f"{tag}Map synthetic worker status {state} into pending, active, held or terminal."
        answer=lookup[state]
    elif domain=="retry_decision":
        statuses=("pre_admission_503","pre_admission_busy","unknown_post_commit",
                  "denied","source_tampered","cancelled")
        state=statuses[index%6]
        prompt=f"{tag}For status {state}, permit retry only for pre-admission transient errors. Answer retry or hold."
        answer="retry" if state.startswith("pre_admission_") else "hold"
    elif domain=="evidence_match":
        actual=f"{a:08x}"
        expected=actual if index%2==0 else f"{a+1:08x}"
        prompt=f"{tag}Observed digest prefix {actual}, pinned prefix {expected}. Reply match or mismatch."
        answer="match" if actual==expected else "mismatch"
    elif domain=="provenance_select":
        prompt=f"{tag}Source old revision 1 says {w}; new revision 2 says {city}. Output the later revision value."
        answer=city
    else:
        reject("challenge-unknown-domain")
    return args,prompt,answer
