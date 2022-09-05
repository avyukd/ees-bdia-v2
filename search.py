import requests
import argparse
import json
from typing import List
from bs4 import BeautifulSoup
from datetime import datetime

def agency_map(raw: List[str]) -> List[str]:
    # raw is a list of string input agencies
    abbrToName = {
        "DOC": "Department of Commerce",
        "DOD": "Department of Defense",
        "DOE": "Department of Energy",
        "ED": "Department of Education",
        "HHS": "Department of Health and Human Services",
        "DHS": "Department of Homeland Security",
        "HUD": "Department of Housing and Urban Development",
        "DOJ": "Department of Justice",
        "DOL": "Department of Labor",
        "DOS": "Department of State",
        "DOI": "Department of the Interior",
        "DOT": "Department of Transportation",
        "USDT": "Department of the Treasury",
        "VA": "Department of Veterans Affairs",
        "EPA": "Environmental Protection Agency",
        "GSA": "General Services Administration",
        "NASA": "National Aeronautics and Space Administration",
        "NSF": "National Science Foundation",
        "NRC": "Nuclear Regulatory Commission",
        "OPM": "Office of Personnel Management",
        "SBA": "Small Business Administration",
        "SSA": "Social Security Administration",
        "USAID": "Agency for International Development",
        "USDA": "Department of Agriculture"
    }
    
    if raw is None:
        return []

    agencies = []
    for rawAgency in raw:
        if rawAgency.upper() in abbrToName:
            agencies.append({
                "type" : "awarding",
                "name" : abbrToName[rawAgency.upper()],
                "tier" : "toptier"
            })    
    return agencies

def parseSbaResponse(response: str, info: dict):
    soup = BeautifulSoup(response, "html.parser")
    #get all divs w/ class "profileline"
    profile_divs = soup.find_all("div", {"class":"profileline"})
    #iterate over profile divs
    for profile_div in profile_divs:
        k = profile_div.find("div", {"class":"profilehead"}).text
        if profile_div.find("div", {"class":"profileinfo"}) is not None:
            v = profile_div.find("div", {"class":"profileinfo"}).text
        info[k]=v
    cap_narr = soup.find(string="Capabilities Narrative:")
    if cap_narr is not None:
        s = cap_narr.find_next('div').text
        cap_narrative = " ".join(s.split())
        info['Capabilities Narrative'] = cap_narrative
    #get past performance
    all_references = soup.find_all("div",{"class":"referencebox"})
    reference_info = []
    for reference in all_references:
        contract_info = {}
        profile_divs = reference.find_all("div", {"class":"profileline"})
        for profile_div in profile_divs:
            k = profile_div.find("div", {"class":"profilehead"}).text
            if profile_div.find("div", {"class":"profileinfo"}) is not None:
                v = profile_div.find("div", {"class":"profileinfo"}).text
            contract_info[k]=v
        reference_info.append(contract_info)
    info['References'] = reference_info

AWARD_SEARCH_REQUEST_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
ENTITY_SEARCH_URL = "https://api.sam.gov/entity-information/v2/entities"
SBA_SEARCH_URL = "https://web.sba.gov/pro-net/search/dsp_profile.cfm"

API_KEY = "Qc3QVsNPUOLgTWDTHnSbFjc2lQ1eoImJXOR2EJ8U"

parser = argparse.ArgumentParser()
parser.add_argument('--keywords', nargs="+",help="keywords for search",required=True)
parser.add_argument('--agencies',nargs="*",help="agency abbreviations",required=False)
parser.add_argument('--max',nargs=1,default=10,help="max number of results",required=False)
parser.add_argument('--debug',nargs=1,default=False,help="if this is true, debug output will be printed. otherwise, just the end json will be printed",required=False)

args = parser.parse_args()

obj = json.load(open("request_default.json"))

obj["filters"]["keywords"] = args.keywords

if isinstance(args.max, int):
    obj["limit"] = args.max
else:
    obj["limit"] = int(args.max[0])

agencies = agency_map(args.agencies)
if len(agencies) > 0:
    obj["filters"]["agencies"] = agencies

if isinstance(args.debug, bool):
    debugFlag = args.debug
else:
    debugFlag = bool(args.debug[0])

response = requests.post(AWARD_SEARCH_REQUEST_URL, json=obj)
results = response.json()["results"]

if debugFlag:
    print("Number of results to process:", len(results), flush=True)

items = []
cnt = 0
for result in results:
    if debugFlag:
        print("Result:",cnt, flush=True)
    
    name = result["Recipient Name"]

    try:
        samResponse = requests.get(ENTITY_SEARCH_URL, params={'legalBusinessName': name, 'api_key': API_KEY})
        
        # if company info is not found, this award will not be included 
        if samResponse.status_code != 200:
            cnt += 1
            continue
        
        samResponse = samResponse.json()

        url = samResponse['entityData'][0]['coreData']["entityInformation"]['entityURL']
        businessTypes = samResponse['entityData'][0]['coreData']["businessTypes"]
        businessTypeList = [x["businessTypeDesc"] for x in businessTypes["businessTypeList"]]
        sba8aEntrance = ""
        sba8aExit = ""
        if "sbaBusinessTypeList" in businessTypes:
            for x in businessTypes["sbaBusinessTypeList"]:
                if x["sbaBusinessTypeDesc"] is not None:
                    businessTypeList.append(x["sbaBusinessTypeDesc"])
                    if "8(a)" in x["sbaBusinessTypeDesc"]:
                        sba8aEntrance = x["certificationEntryDate"]
                        sba8aExit = x["certificationExitDate"]
        
        socio_economic_status = []
        SBA8aFlag = False
        for d in businessTypeList:
            if not ("corporation" in d.lower() or "organization" in d.lower()):
                socio_economic_status.append(d)
        
        primaryNaics = samResponse['entityData'][0]['assertions']["goodsAndServices"]['primaryNaics']

        info = {
            "award" : result,
            "company" : {
                "url": url,
                "primaryNaics": primaryNaics,
                "socioEconomicStatus": socio_economic_status,
                "sba8aEntrance": sba8aEntrance,
                "sba8aExit": sba8aExit
            }
        }

        # call sba search api
        ueiSAM = samResponse['entityData'][0]['entityRegistration']["ueiSAM"]
        sbaResponse = requests.get(SBA_SEARCH_URL, params={'SAM_UEI': ueiSAM})

        if sbaResponse.status_code != 200:
            items.append(info)
            cnt += 1
            continue

        sbaResponse = sbaResponse.text
        parseSbaResponse(sbaResponse, info)
        items.append(info)
        
        cnt += 1
    except Exception as e:
        if debugFlag:
            print(name, e, flush=True)
        continue

res = json.dumps(items)
stamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
with open(f"results/results_{stamp}.json", "w") as f:
    f.write(res)
print(res, flush=True)