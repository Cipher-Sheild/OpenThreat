"""Build the novelty benchmark: (older sentence, newer sentence, gold label) pairs.

Each item states ONE fact in the old text and ONE fact in the new text. The gold label is what a
careful analyst would assign under the agreed policy (docs/contracts/CHANGELOG.md), NOT what our
pipeline happens to output: several categories are deliberately hard (typos, look-alike names,
hedged wording, revisions without keywords) so the pipeline is not guaranteed to be right.

Output: evaluation/data/novelty_benchmark.jsonl and novelty_benchmark_review.csv. The CSV is for
the two members to check every label by hand (fill the `verified_by` column) before the numbers
go into the report.

    python evaluation/build_novelty_benchmark.py
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
OLD, NEW = "2024-01-15T00:00:00Z", "2024-06-20T00:00:00Z"
OLDER = "2023-05-01T00:00:00Z"

items: list[dict] = []


def add(category, old, new, gold, old_date=OLD, new_date=NEW, note=""):
    items.append({"category": category, "old_text": old, "old_date": old_date, "new_text": new,
                  "new_date": new_date, "gold": gold, "note": note})


# ---------------------------------------------------------------- KNOWN: same fact, same names
same = [
    ("APT28 used Mimikatz to dump credentials.", "In the latest intrusion, APT28 again used Mimikatz."),
    ("Lazarus Group deployed AppleJeus on victim machines.", "Lazarus Group deployed AppleJeus through fake trading apps."),
    ("FIN7 exploited CVE-2021-44228 to gain access.", "FIN7 exploited CVE-2021-44228 against exposed servers."),
    ("APT41 used PlugX in several campaigns.", "APT41 continued to use PlugX in 2024."),
    ("Turla used Mimikatz during lateral movement.", "Turla used Mimikatz to move laterally inside the network."),
    ("Wizard Spider deployed Ryuk ransomware.", "Wizard Spider deployed Ryuk ransomware once again."),
    ("APT29 targeted the government sector in Europe.", "APT29 targeted the government sector across several countries."),
    ("Sandworm Team targeted the energy sector in Ukraine.", "Sandworm Team targeted the energy sector again this winter."),
    ("The Snake implant is attributed to Turla.", "Analysts agree that the Snake implant is attributed to Turla."),
    ("Kimsuky used PowerShell scripts for reconnaissance.", "Kimsuky used PowerShell during the operation."),
    ("APT33 targeted the aviation sector.", "APT33 targeted the aviation sector in the Middle East."),
    ("menuPass used PlugX against managed service providers.", "menuPass used PlugX in a new wave of attacks."),
    ("Emotet dropped TrickBot on infected hosts.", "Emotet dropped TrickBot in the latest spam campaign."),
    ("APT28 exploited CVE-2023-23397 in Microsoft Outlook.", "APT28 exploited CVE-2023-23397 to steal NTLM hashes."),
    ("Conti operators used Cobalt Strike for command and control.", "Conti operators used Cobalt Strike beacons on many hosts."),
]
for o, n in same:
    add("KNOWN_same_names", o, n, "KNOWN")

# ---------------------------------------------------------------- KNOWN: alias / spelling variants
alias = [
    ("APT28 used Mimikatz to dump credentials.", "Fancy Bear used Mimikatz to harvest passwords."),
    ("APT29 deployed SUNBURST through the SolarWinds update.", "Cozy Bear deployed SUNBURST via a trojanised update."),
    ("Lazarus Group targeted the financial sector.", "Hidden Cobra targeted the financial sector worldwide."),
    ("Sandworm Team deployed NotPetya.", "Voodoo Bear deployed NotPetya against Ukrainian companies."),
    ("APT1 used Mimikatz on compromised hosts.", "Comment Crew used Mimikatz on compromised hosts."),
    ("APT35 targeted the government sector.", "Charming Kitten targeted the government sector in the region."),
    ("MuddyWater used PowerShell for execution.", "Seedworm used PowerShell to run its payloads."),
    ("Wizard Spider deployed Ryuk.", "UNC1878 deployed Ryuk in hospital networks."),
    ("APT28 used Cobalt Strike for post-exploitation.", "APT 28 used CobaltStrike for post-exploitation."),
    ("Emotet dropped QakBot on infected machines.", "Emotet dropped Qbot on infected machines."),
    ("APT41 used China Chopper web shells.", "Wicked Panda used China Chopper on web servers."),
    ("Turla deployed Uroburos in government networks.", "Venomous Bear deployed the Snake rootkit in government networks."),
    ("APT32 targeted the automotive sector.", "OceanLotus targeted the automotive sector."),
    ("FIN7 used Carbanak against retailers.", "Carbanak was used by FIN7 against retailers.", ),
    ("APT10 used PlugX in the Cloud Hopper campaign.", "menuPass used PlugX during Operation Cloud Hopper."),
]
for o, n in alias:
    add("KNOWN_alias", o, n, "KNOWN", note="same entities under an alias, spelling variant or passive voice")

# ---------------------------------------------------------------- KNOWN: paraphrased relation verb
para = [
    ("APT28 used Mimikatz.", "APT28 leveraged Mimikatz to obtain credentials."),
    ("Lazarus Group used AppleJeus.", "Lazarus Group relied on AppleJeus to access crypto wallets."),
    ("APT29 used Cobalt Strike.", "APT29 employed Cobalt Strike for persistence."),
    ("FIN7 exploited CVE-2021-44228.", "FIN7 took advantage of CVE-2021-44228 for initial access."),
    ("Turla targeted the defense sector.", "Turla went after the defense sector in Europe."),
    ("Sandworm Team targeted the energy sector.", "The energy sector was targeted by Sandworm Team."),
    ("Emotet delivered TrickBot.", "Emotet dropped TrickBot as a second-stage payload."),
    ("APT41 used Mimikatz.", "Mimikatz was used by APT41 during the intrusion."),
    ("Kimsuky targeted the government sector.", "Kimsuky attacked the government sector in South Korea."),
    ("APT33 used PowerShell.", "APT33 utilized PowerShell to execute commands."),
]
for o, n in para:
    add("KNOWN_paraphrase", o, n, "KNOWN")

# ---------------------------------------------------------------- KNOWN that string matching gets wrong (typo)
typo = [
    ("APT28 used Mimikatz.", "APT28 used Mimkatz to dump credentials.", "one-letter typo in the tool name"),
    ("Lazarus Group deployed AppleJeus.", "Lazarus Group deployed Applejeus again.", "case variant"),
    ("APT29 used Cobalt Strike.", "APT29 used Cobalt-Strike beacons.", "hyphenated variant"),
    ("FIN7 used Carbanak.", "FIN7 used Carbanac in the attack.", "misspelled malware name"),
    ("Turla used Mimikatz.", "Turla used Mimikats on the domain controller.", "misspelled tool name"),
]
for o, n, why in typo:
    add("KNOWN_typo", o, n, "KNOWN", note=why)

# ---------------------------------------------------------------- NEW: nothing on record for the subject
new_subject = [
    ("APT28 used Mimikatz.", "APT41 used Mimikatz during the campaign."),
    ("Lazarus Group deployed AppleJeus.", "Kimsuky deployed AppleSeed against diplomats."),
    ("FIN7 exploited CVE-2021-44228.", "Wizard Spider exploited CVE-2021-44228."),
    ("Turla used Mimikatz.", "APT33 used Mimikatz on Windows servers."),
    ("APT29 targeted the government sector.", "Sandworm Team targeted the government sector."),
    ("Emotet dropped TrickBot.", "BazarLoader dropped Cobalt Strike."),
    ("APT28 targeted the defense sector.", "APT32 targeted the defense sector."),
    ("APT41 used PlugX.", "MuddyWater used PowerShell for persistence."),
    ("The Snake implant is attributed to Turla.", "The Industroyer malware is attributed to Sandworm Team."),
    ("APT29 used Cobalt Strike.", "FIN7 used Cobalt Strike against hospitality companies."),
]
for o, n in new_subject:
    add("NEW_other_subject", o, n, "NEW")

# ---------------------------------------------------------------- NEW: same subject, new object (multi-valued)
new_object = [
    ("APT28 used Mimikatz.", "APT28 used Responder to capture hashes."),
    ("APT28 used Mimikatz.", "APT28 deployed HeadLace, a backdoor, on the victim network."),
    ("Lazarus Group deployed AppleJeus.", "Lazarus Group deployed Dtrack against a nuclear plant."),
    ("FIN7 exploited CVE-2021-44228.", "FIN7 exploited CVE-2023-34362 in MOVEit Transfer."),
    ("APT29 targeted the government sector.", "APT29 targeted the healthcare sector during the pandemic."),
    ("Turla used Mimikatz.", "Turla used PowerShell to load payloads in memory."),
    ("Sandworm Team deployed NotPetya.", "Sandworm Team deployed Industroyer against substations."),
    ("APT41 used PlugX.", "APT41 used ShadowPad in supply-chain attacks."),
    ("Wizard Spider deployed Ryuk.", "Wizard Spider deployed Conti ransomware."),
    ("APT33 targeted the aviation sector.", "APT33 targeted the energy sector as well."),
    ("Kimsuky used PowerShell.", "Kimsuky used Mimikatz to steal credentials."),
    ("Emotet dropped TrickBot.", "Emotet dropped QakBot in a new campaign."),
    ("APT28 exploited CVE-2023-23397.", "APT28 exploited CVE-2022-38028 in the Windows Print Spooler."),
    ("MuddyWater used PowerShell.", "MuddyWater used ScreenConnect for remote access."),
    ("APT32 targeted the automotive sector.", "APT32 targeted the media sector in Vietnam."),
    ("APT29 used Cobalt Strike.", "APT29 deployed WellMess on compromised servers."),
    ("menuPass used PlugX.", "menuPass used QuasarRAT in the same operation."),
    ("APT28 targeted the defense sector.", "APT28 targeted the energy sector in Poland."),
    ("FIN7 used Carbanak.", "FIN7 used Lizar, a new toolkit, against its victims."),
    ("Sandworm Team targeted the energy sector.", "Sandworm Team targeted the telecommunications sector."),
]
for o, n in new_object:
    add("NEW_new_object", o, n, "NEW", note="multi-valued relation: old fact stays ACTIVE")

# ---------------------------------------------------------------- NEW that string similarity gets wrong (look-alikes)
lookalike = [
    ("APT28 used Mimikatz.", "APT29 used Mimikatz.", "APT28 and APT29 are different groups"),
    ("FIN7 exploited CVE-2023-23397.", "FIN7 exploited CVE-2023-23398.", "different CVE"),
    ("APT33 targeted the aviation sector.", "APT34 targeted the aviation sector.", "different group"),
    ("Wizard Spider deployed Ryuk.", "Wizard Spider deployed Conti.", "different ransomware"),
    ("APT41 used PlugX.", "APT40 used PlugX.", "different group"),
    ("Emotet dropped TrickBot.", "Emotet dropped IcedID.", "different payload"),
    ("APT28 exploited CVE-2021-40444.", "APT28 exploited CVE-2021-44228.", "different CVE"),
    ("Turla used Mimikatz.", "Turla used LaZagne to recover passwords.", "different credential tool"),
    ("APT32 targeted the automotive sector.", "APT32 targeted the aviation sector.", "different sector"),
    ("FIN6 used Cobalt Strike.", "FIN7 used Cobalt Strike.", "different group"),
]
for o, n, why in lookalike:
    add("NEW_lookalike", o, n, "NEW", note=why)

# ---------------------------------------------------------------- UPDATED: attribution changes in a newer report
attr_upd = [
    ("The Snake implant is attributed to Turla.", "Researchers now attribute the Snake implant to APT29."),
    ("The NotPetya malware is attributed to Lazarus Group.", "NotPetya is attributed to Sandworm Team after a joint investigation."),
    ("SUNBURST is attributed to APT41.", "SUNBURST was attributed to APT29 by several governments."),
    ("WellMess is attributed to APT28.", "WellMess has since been attributed to APT29."),
    ("Industroyer is attributed to Dragonfly.", "Industroyer is now attributed to Sandworm Team."),
    ("Olympic Destroyer is attributed to Lazarus Group.", "Olympic Destroyer was later attributed to Sandworm Team."),
    ("The ShadowPad backdoor is attributed to APT10.", "ShadowPad is attributed to APT41 in the updated assessment."),
    ("Ryuk is attributed to Lazarus Group.", "Ryuk is attributed to Wizard Spider."),
    ("BlackEnergy is attributed to APT28.", "BlackEnergy is attributed to Sandworm Team."),
    ("Zebrocy is attributed to Turla.", "Zebrocy is attributed to APT28 according to new evidence."),
    ("Carbanak is attributed to FIN6.", "Carbanak is attributed to FIN7."),
    ("TrickBot is attributed to FIN7.", "TrickBot was attributed to Wizard Spider."),
    ("Emotet is attributed to TA542.", "Emotet is now attributed to Mummy Spider."),
    ("PlugX is attributed to APT1.", "PlugX is attributed to menuPass in this report."),
    ("Kazuar is attributed to APT29.", "Kazuar was re-attributed to Turla."),
]
for o, n in attr_upd:
    add("UPDATED_attribution", o, n, "UPDATED", note="ATTRIBUTED_TO is single-valued; newer report supersedes")
# Emotet/Mummy Spider and TA542 are aliases in some sources: keep honest gold
items[-3]["gold"] = "KNOWN"
items[-3]["note"] = "TA542 and Mummy Spider are names for the same Emotet operators -> same attribution (hard: needs alias knowledge)"

# ---------------------------------------------------------------- UPDATED: "no longer" in a newer report
no_longer = [
    ("APT29 used WellMess.", "APT29 no longer uses WellMess."),
    ("Turla used Mimikatz.", "Turla has stopped using Mimikatz."),
    ("Lazarus Group used AppleJeus.", "Lazarus Group no longer uses AppleJeus in its operations."),
    ("FIN7 used Carbanak.", "FIN7 abandoned Carbanak in favour of newer tools."),
    ("APT28 used X-Agent.", "APT28 has ceased using X-Agent."),
    ("Wizard Spider deployed Ryuk.", "Wizard Spider no longer deploys Ryuk."),
    ("Emotet dropped TrickBot.", "Emotet no longer drops TrickBot."),
    ("APT41 used PlugX.", "APT41 retired PlugX from its toolkit."),
    ("Sandworm Team used BlackEnergy.", "Sandworm Team stopped using BlackEnergy after 2016."),
    ("APT33 used PowerShell.", "APT33 no longer relies on PowerShell."),
]
for o, n in no_longer:
    add("UPDATED_no_longer", o, n, "UPDATED", note="newer report says the fact stopped being true")

# ---------------------------------------------------------------- CONFLICTING: attribution disagreement, not newer
attr_conf = [
    ("The Snake implant is attributed to Turla.", "The Snake implant is attributed to APT29."),
    ("NotPetya is attributed to Sandworm Team.", "NotPetya is attributed to Lazarus Group."),
    ("SUNBURST is attributed to APT29.", "SUNBURST is attributed to APT41."),
    ("WellMess is attributed to APT29.", "WellMess is attributed to APT28."),
    ("Industroyer is attributed to Sandworm Team.", "Industroyer is attributed to Dragonfly."),
    ("Ryuk is attributed to Wizard Spider.", "Ryuk is attributed to Lazarus Group."),
    ("Zebrocy is attributed to APT28.", "Zebrocy is attributed to Turla."),
    ("Carbanak is attributed to FIN7.", "Carbanak is attributed to FIN6."),
    ("TrickBot is attributed to Wizard Spider.", "TrickBot is attributed to FIN7."),
    ("ShadowPad is attributed to APT41.", "ShadowPad is attributed to APT10."),
    ("BlackEnergy is attributed to Sandworm Team.", "BlackEnergy is attributed to APT28."),
    ("Kazuar is attributed to Turla.", "Kazuar is attributed to APT29."),
]
for o, n in attr_conf:
    # the "new" report is OLDER than the stored one -> it cannot supersede it
    add("CONFLICTING_attribution", o, n, "CONFLICTING", old_date=NEW, new_date=OLDER,
        note="different attribution from an older source: sources disagree")

# ---------------------------------------------------------------- CONFLICTING: denial of an active fact
denial = [
    ("APT28 used Mimikatz.", "There is no evidence that APT28 used Mimikatz."),
    ("Turla used Mimikatz.", "Turla did not use Mimikatz in this campaign."),
    ("The Snake implant is attributed to Turla.", "The Snake implant is not attributed to Turla."),
    ("Lazarus Group deployed AppleJeus.", "Lazarus Group never deployed AppleJeus, contrary to earlier claims."),
    ("FIN7 exploited CVE-2021-44228.", "FIN7 did not exploit CVE-2021-44228."),
    ("APT29 targeted the healthcare sector.", "APT29 did not target the healthcare sector, the report clarifies."),
    ("Wizard Spider deployed Ryuk.", "Analysts dispute that Wizard Spider deployed Ryuk."),
    ("Emotet dropped TrickBot.", "Emotet was falsely linked to TrickBot deliveries; it never dropped TrickBot."),
    ("APT41 used PlugX.", "APT41 has never used PlugX according to the vendor."),
    ("NotPetya is attributed to Sandworm Team.", "NotPetya is incorrectly attributed to Sandworm Team, the group claims."),
]
for o, n in denial:
    add("CONFLICTING_denial", o, n, "CONFLICTING", old_date=NEW, new_date=OLDER,
        note="denial of a recorded fact without saying it stopped")

# ---------------------------------------------------------------- UNCERTAIN: hedged / weak statements
uncertain = [
    ("APT28 used Mimikatz.", "A tool resembling Mimikatz may have been used by an unknown actor."),
    ("Lazarus Group deployed AppleJeus.", "Some researchers loosely associate AppleJeus with an unnamed cluster."),
    ("Turla used Mimikatz.", "It is unclear whether Turla or another group used Mimikatz."),
    ("APT29 used Cobalt Strike.", "Cobalt Strike activity was possibly associated with APT29, with low confidence."),
    ("FIN7 used Carbanak.", "Carbanak samples were seen near infrastructure that might belong to FIN7."),
    ("The Snake implant is attributed to Turla.", "The Snake implant is perhaps associated with APT29."),
    ("Wizard Spider deployed Ryuk.", "Ryuk could be associated with Wizard Spider or with affiliates."),
    ("APT41 used PlugX.", "PlugX may be associated with APT41, but the evidence is thin."),
    ("Kimsuky used PowerShell.", "Kimsuky is possibly associated with PowerShell-based activity."),
    ("Emotet dropped TrickBot.", "TrickBot was possibly associated with Emotet infections."),
]
for o, n in uncertain:
    add("UNCERTAIN_hedged", o, n, "UNCERTAIN", note="hedged wording: an analyst would not assert the fact")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    random.Random(7).shuffle(items)
    for i, it in enumerate(items, 1):
        it["id"] = f"N{i:03d}"
    with open(OUT / "novelty_benchmark.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(OUT / "novelty_benchmark_review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "old_text", "old_date", "new_text", "new_date", "gold", "note",
                    "agree (Y/N)", "corrected_gold", "verified_by"])
        for it in sorted(items, key=lambda x: x["id"]):
            w.writerow([it["id"], it["category"], it["old_text"], it["old_date"][:10], it["new_text"],
                        it["new_date"][:10], it["gold"], it["note"], "", "", ""])
    from collections import Counter
    print(len(items), Counter(it["gold"] for it in items))


if __name__ == "__main__":
    main()
