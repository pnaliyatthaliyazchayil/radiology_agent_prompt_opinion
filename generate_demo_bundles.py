"""
Generate 10 synthetic patient FHIR R4 bundles for CritCom demo.

- No ACR category tag on any DiagnosticReport (LLM classifier does the work)
- 5 Cat1 patients (immediate critical), 3 Cat2 (urgent), 2 Cat3 (routine)
- Each bundle is self-contained: Patient, Practitioner, PractitionerRole,
  ServiceRequest, DiagnosticReport, plus an on-call Practitioner/Role
- POST + urn:uuid transaction style (Synthea-compatible). The FHIR server
  assigns IDs at import and rewrites cross-references automatically — required
  for Prompt Opinion to import the bundle and link CritCom to the right patient.
- Run: python generate_demo_bundles.py
  Output: demo_bundles/patient-001.json ... patient-010.json
"""

import base64
import json
import os
import uuid

OUT_DIR = "demo_bundles"
os.makedirs(OUT_DIR, exist_ok=True)

NOW = "2026-05-08T10:00:00+00:00"

# Stable identifier system so re-imports are idempotent (HAPI ifNoneExist match).
ID_SYS = "https://promptopinion.ai/critcom/demo"


def _u() -> str:
    """Fresh urn:uuid: id."""
    return f"urn:uuid:{uuid.uuid4()}"

# ---------------------------------------------------------------------------
# Patient data — (first, last, dob, gender)
# ---------------------------------------------------------------------------
PATIENTS = [
    # Cat1 — immediate critical findings
    {
        "n": 1, "first": "Harold", "last": "Simmons", "dob": "1958-03-14", "gender": "male",
        "doc_first": "Sarah", "doc_last": "Patel", "doc_email": "spatel@metro-hospital.org",
        "doc_phone": "317-555-1101", "doc_pager": "317-555-2101",
        "study": "CT Chest without contrast",
        "loinc": "24627-2", "loinc_display": "CT Chest",
        "reason": "Sudden onset dyspnea and hypoxia",
        "priority": "stat",
        "report": (
            "CLINICAL INDICATION: 67-year-old male with sudden onset severe dyspnea, "
            "oxygen saturation 82% on room air, tracheal deviation noted on exam.\n\n"
            "TECHNIQUE: CT of the chest without intravenous contrast.\n\n"
            "FINDINGS:\n"
            "PLEURAL SPACE: There is a large right-sided pneumothorax occupying approximately "
            "65% of the right hemithorax. The right lung is collapsed to the hilum. "
            "The mediastinum is shifted significantly to the left. The trachea deviates "
            "leftward at the level of the carina. The right hemidiaphragm is depressed. "
            "There is no left-sided pleural effusion or pneumothorax.\n\n"
            "HEART: The cardiac silhouette appears compressed. The superior vena cava "
            "is narrow, consistent with decreased venous return.\n\n"
            "LUNGS: Left lung is hyperinflated and clear. No consolidation.\n\n"
            "IMPRESSION:\n"
            "1. Large right-sided tension pneumothorax with mediastinal shift and tracheal "
            "deviation. Immediate chest tube decompression is required.\n"
            "2. Left lung clear."
        ),
    },
    {
        "n": 2, "first": "Maria", "last": "Gonzalez", "dob": "1971-09-22", "gender": "female",
        "doc_first": "Thomas", "doc_last": "Brennan", "doc_email": "tbrennan@citymed.org",
        "doc_phone": "317-555-1102", "doc_pager": "317-555-2102",
        "study": "CT Head without contrast",
        "loinc": "24725-4", "loinc_display": "CT Head",
        "reason": "Sudden onset worst headache of life",
        "priority": "stat",
        "report": (
            "CLINICAL INDICATION: 54-year-old female presenting with thunderclap headache, "
            "neck stiffness, and photophobia. GCS 14.\n\n"
            "TECHNIQUE: Non-contrast CT of the brain.\n\n"
            "FINDINGS:\n"
            "SUBARACHNOID SPACE: Diffuse hyperdensity is identified within the basal cisterns, "
            "Sylvian fissures bilaterally, and along the tentorium cerebelli, consistent with "
            "acute subarachnoid hemorrhage. The pattern is most prominent in the "
            "suprasellar cistern and right Sylvian fissure.\n\n"
            "VENTRICLES: Mild hydrocephalus with temporal horn rounding bilaterally. "
            "The third ventricle measures 7mm (upper limit of normal).\n\n"
            "BRAIN PARENCHYMA: No intraparenchymal hematoma. No midline shift. "
            "Gray-white differentiation is preserved.\n\n"
            "IMPRESSION:\n"
            "1. Acute subarachnoid hemorrhage with diffuse basal cistern involvement. "
            "Neurosurgical consultation required immediately.\n"
            "2. Early communicating hydrocephalus — monitor closely.\n"
            "3. CTA of the head recommended urgently to evaluate for ruptured aneurysm."
        ),
    },
    {
        "n": 3, "first": "David", "last": "Nakamura", "dob": "1945-11-05", "gender": "male",
        "doc_first": "Linda", "doc_last": "Morrison", "doc_email": "lmorrison@regionalmc.org",
        "doc_phone": "317-555-1103", "doc_pager": "317-555-2103",
        "study": "CT Chest/Abdomen/Pelvis with contrast",
        "loinc": "24627-2", "loinc_display": "CT Chest",
        "reason": "Tearing chest pain radiating to back",
        "priority": "stat",
        "report": (
            "CLINICAL INDICATION: 80-year-old male with acute onset tearing chest pain "
            "radiating to the back, blood pressure differential between arms of 30 mmHg.\n\n"
            "TECHNIQUE: CT angiography of the chest, abdomen, and pelvis with IV contrast.\n\n"
            "FINDINGS:\n"
            "AORTA: An intimal flap is identified originating 1.2 cm above the sinotubular "
            "junction, extending inferiorly through the descending thoracic aorta to the "
            "level of the renal arteries. The true lumen is compressed. The false lumen "
            "demonstrates delayed enhancement. Maximum aortic diameter at the level of the "
            "arch is 5.4 cm. The coronary ostia arise from the true lumen. "
            "The celiac and superior mesenteric arteries arise from the true lumen.\n\n"
            "PERICARDIUM: Small pericardial effusion measuring up to 6 mm. "
            "No CT signs of tamponade.\n\n"
            "IMPRESSION:\n"
            "1. Type A aortic dissection involving the ascending aorta and extending "
            "to the renal arteries. This is a surgical emergency requiring emergent "
            "cardiothoracic surgical consultation.\n"
            "2. Small pericardial effusion — monitor for evolution to tamponade."
        ),
    },
    {
        "n": 4, "first": "Priya", "last": "Sharma", "dob": "1989-06-18", "gender": "female",
        "doc_first": "Kevin", "doc_last": "Walsh", "doc_email": "kwalsh@universityhospital.edu",
        "doc_phone": "317-555-1104", "doc_pager": "317-555-2104",
        "study": "MRI Brain with and without contrast",
        "loinc": "24590-2", "loinc_display": "MRI Brain",
        "reason": "Acute onset left sided weakness and aphasia",
        "priority": "stat",
        "report": (
            "CLINICAL INDICATION: 36-year-old female with sudden onset left-sided "
            "hemiplegia and expressive aphasia. Last known well 45 minutes ago.\n\n"
            "TECHNIQUE: MRI of the brain with diffusion weighted imaging, FLAIR, "
            "T1, T2, and post-contrast T1 sequences.\n\n"
            "FINDINGS:\n"
            "DIFFUSION: Restricted diffusion is identified in the right MCA territory "
            "involving the right frontal and parietal lobes, right basal ganglia, and "
            "right insula. The involved area measures approximately 85 mL by ASPECTS scoring "
            "(ASPECTS 4). No hemorrhagic transformation.\n\n"
            "MRA: Occlusion of the right middle cerebral artery at the M1 segment. "
            "No flow-related enhancement distal to the occlusion.\n\n"
            "IMPRESSION:\n"
            "1. Large right MCA territory acute ischemic stroke with M1 occlusion. "
            "Patient is within thrombectomy window — emergent neurovascular intervention "
            "team activation required immediately.\n"
            "2. No hemorrhagic transformation currently."
        ),
    },
    {
        "n": 5, "first": "Robert", "last": "Fleming", "dob": "1963-02-28", "gender": "male",
        "doc_first": "Angela", "doc_last": "Torres", "doc_email": "atorres@northside-health.org",
        "doc_phone": "317-555-1105", "doc_pager": "317-555-2105",
        "study": "CT Abdomen/Pelvis with contrast",
        "loinc": "24550-6", "loinc_display": "CT Abdomen",
        "reason": "Acute severe abdominal pain and rigidity",
        "priority": "stat",
        "report": (
            "CLINICAL INDICATION: 62-year-old male with sudden onset severe generalized "
            "abdominal pain, board-like rigidity on exam, and fever of 38.9°C.\n\n"
            "TECHNIQUE: CT of the abdomen and pelvis with intravenous contrast.\n\n"
            "FINDINGS:\n"
            "PERITONEUM: Pneumoperitoneum is identified with free air beneath the right "
            "hemidiaphragm measuring up to 3.2 cm in craniocaudal extent. Free air is also "
            "noted in the perihepatic space and along the anterior peritoneal surface. "
            "Moderate free fluid is present throughout the peritoneal cavity.\n\n"
            "BOWEL: The stomach and proximal duodenum demonstrate wall thickening. "
            "No discrete perforation site identified, however the region of the first "
            "portion of the duodenum is suspicious.\n\n"
            "IMPRESSION:\n"
            "1. Large pneumoperitoneum consistent with hollow viscus perforation. "
            "Emergent surgical consultation required.\n"
            "2. Peritoneal free fluid consistent with peritonitis.\n"
            "3. Duodenal perforation suspected — correlate clinically."
        ),
    },
    # Cat2 — urgent findings
    {
        "n": 6, "first": "Catherine", "last": "Dubois", "dob": "1955-07-11", "gender": "female",
        "doc_first": "Marcus", "doc_last": "Hill", "doc_email": "mhill@lakesidemedical.org",
        "doc_phone": "317-555-1106", "doc_pager": "317-555-2106",
        "study": "CT Chest with contrast",
        "loinc": "24627-2", "loinc_display": "CT Chest",
        "reason": "Progressive dyspnea and pleuritic chest pain",
        "priority": "urgent",
        "report": (
            "CLINICAL INDICATION: 70-year-old female with two weeks of progressive exertional "
            "dyspnea and right-sided pleuritic chest pain. Recent long-haul flight.\n\n"
            "TECHNIQUE: CT pulmonary angiography.\n\n"
            "FINDINGS:\n"
            "PULMONARY ARTERIES: Filling defects are identified in the right main pulmonary "
            "artery extending into the right upper, middle, and lower lobe segmental arteries. "
            "Additional filling defects are present in the left lower lobe segmental arteries. "
            "No evidence of right heart strain on CT — the RV/LV ratio is 0.9.\n\n"
            "LUNGS: Small right pleural effusion. A wedge-shaped peripheral opacity in the "
            "right lower lobe is consistent with pulmonary infarction.\n\n"
            "IMPRESSION:\n"
            "1. Bilateral pulmonary emboli — right main pulmonary artery and bilateral "
            "segmental branches. Non-massive by RV/LV ratio criteria.\n"
            "2. Right lower lobe pulmonary infarction.\n"
            "3. Anticoagulation and hematology/pulmonology consultation recommended "
            "within 24 hours."
        ),
    },
    {
        "n": 7, "first": "James", "last": "Okonkwo", "dob": "1968-04-03", "gender": "male",
        "doc_first": "Rebecca", "doc_last": "Huang", "doc_email": "rhuang@eastside-clinic.org",
        "doc_phone": "317-555-1107", "doc_pager": "317-555-2107",
        "study": "CT Chest with contrast",
        "loinc": "24627-2", "loinc_display": "CT Chest",
        "reason": "Incidental finding on routine chest CT",
        "priority": "routine",
        "report": (
            "CLINICAL INDICATION: 57-year-old male, smoker, routine follow-up chest CT.\n\n"
            "TECHNIQUE: CT of the chest with intravenous contrast.\n\n"
            "FINDINGS:\n"
            "LUNGS: A spiculated right upper lobe nodule measuring 2.3 x 1.9 cm is identified "
            "in the right upper lobe, anterior segment. The nodule demonstrates irregular "
            "margins and pleural tethering. There is ipsilateral mediastinal lymphadenopathy "
            "with a right paratracheal node measuring 1.8 x 1.4 cm (short axis). "
            "No contralateral adenopathy. No pleural effusion.\n\n"
            "PRIOR IMAGING: No prior chest CT available for comparison.\n\n"
            "IMPRESSION:\n"
            "1. 2.3 cm spiculated right upper lobe nodule with ipsilateral mediastinal "
            "adenopathy — highly suspicious for primary lung malignancy. "
            "PET-CT and tissue sampling recommended within 24-48 hours.\n"
            "2. Findings represent at minimum stage IIA disease pending further workup."
        ),
    },
    {
        "n": 8, "first": "Susan", "last": "Blackwood", "dob": "1980-12-30", "gender": "female",
        "doc_first": "Daniel", "doc_last": "Reeves", "doc_email": "dreeves@women-health.org",
        "doc_phone": "317-555-1108", "doc_pager": "317-555-2108",
        "study": "CT Abdomen/Pelvis with contrast",
        "loinc": "24550-6", "loinc_display": "CT Abdomen",
        "reason": "Acute right lower quadrant pain",
        "priority": "urgent",
        "report": (
            "CLINICAL INDICATION: 45-year-old female with 18 hours of right lower quadrant pain, "
            "nausea, and fever of 38.4°C. Elevated WBC 14.2.\n\n"
            "TECHNIQUE: CT of the abdomen and pelvis with oral and intravenous contrast.\n\n"
            "FINDINGS:\n"
            "APPENDIX: The appendix is identified measuring 11 mm in maximal diameter with "
            "periappendiceal fat stranding and a small amount of free fluid in the right iliac "
            "fossa. An appendicolith is present at the base. Wall enhancement is increased. "
            "No perforation identified on this examination, however there is adjacent fat "
            "stranding extending to the right lateral abdominal wall.\n\n"
            "IMPRESSION:\n"
            "1. Acute appendicitis with appendicolith. No perforation at this time.\n"
            "2. Surgical consultation recommended urgently to prevent perforation.\n"
            "3. IV antibiotics recommended pending surgical evaluation."
        ),
    },
    # Cat3 — routine findings
    {
        "n": 9, "first": "George", "last": "Petrov", "dob": "1952-08-17", "gender": "male",
        "doc_first": "Nina", "doc_last": "Johansson", "doc_email": "njohansson@generalpractice.org",
        "doc_phone": "317-555-1109", "doc_pager": "317-555-2109",
        "study": "X-Ray Lumbar Spine",
        "loinc": "24969-0", "loinc_display": "XR Lumbar spine",
        "reason": "Chronic low back pain",
        "priority": "routine",
        "report": (
            "CLINICAL INDICATION: 73-year-old male with longstanding low back pain, "
            "no radicular symptoms, no bowel or bladder dysfunction.\n\n"
            "TECHNIQUE: AP and lateral radiographs of the lumbar spine.\n\n"
            "FINDINGS:\n"
            "ALIGNMENT: Mild lumbar spondylosis. Preservation of normal lumbar lordosis. "
            "No spondylolisthesis.\n\n"
            "VERTEBRAL BODIES: Mild anterior osteophyte formation at L2-L3, L3-L4, and L4-L5. "
            "Disc space heights are mildly reduced at L4-L5 and L5-S1 consistent with "
            "degenerative disc disease. No acute fracture or compression deformity.\n\n"
            "SOFT TISSUES: No paravertebral soft tissue abnormality.\n\n"
            "IMPRESSION:\n"
            "1. Multilevel lumbar spondylosis and degenerative disc disease, most pronounced "
            "at L4-L5 and L5-S1. Findings are consistent with chronic degenerative changes.\n"
            "2. No acute osseous abnormality.\n"
            "3. Clinical correlation and conservative management recommended. "
            "MRI may be considered if symptoms worsen or fail to respond to therapy."
        ),
    },
    {
        "n": 10, "first": "Amelia", "last": "Richardson", "dob": "1995-01-25", "gender": "female",
        "doc_first": "Omar", "doc_last": "Khalid", "doc_email": "okhalid@campus-health.edu",
        "doc_phone": "317-555-1110", "doc_pager": "317-555-2110",
        "study": "Ultrasound Right Upper Quadrant",
        "loinc": "24558-9", "loinc_display": "US Abdomen",
        "reason": "Intermittent right upper quadrant discomfort",
        "priority": "routine",
        "report": (
            "CLINICAL INDICATION: 30-year-old female with several months of intermittent "
            "right upper quadrant discomfort, worse after fatty meals.\n\n"
            "TECHNIQUE: Real-time ultrasound of the right upper quadrant.\n\n"
            "FINDINGS:\n"
            "GALLBLADDER: The gallbladder is well-visualized and contains multiple echogenic "
            "foci with posterior acoustic shadowing consistent with cholelithiasis. "
            "The largest calculus measures 8 mm. The gallbladder wall measures 2 mm in "
            "thickness. No pericholecystic fluid. Murphy sign negative on imaging.\n\n"
            "BILIARY: Common bile duct measures 3 mm in diameter, within normal limits. "
            "No intra- or extrahepatic biliary dilatation.\n\n"
            "LIVER: Normal size, echogenicity, and contour. No focal lesion.\n\n"
            "IMPRESSION:\n"
            "1. Cholelithiasis without sonographic evidence of acute cholecystitis.\n"
            "2. Symptoms are consistent with biliary colic. Surgery referral for elective "
            "cholecystectomy may be considered.\n"
            "3. No emergent intervention required."
        ),
    },
]


def make_bundle(p: dict) -> dict:
    n = p["n"]

    # Per-bundle urn:uuid: refs — server assigns real IDs and rewrites these.
    pat_u = _u()
    prac_u = _u()
    role_u = _u()
    sr_u = _u()
    dr_u = _u()
    docref_u = _u()
    oncall_prac_u = _u()
    oncall_role_u = _u()

    # Stable demo identifiers so re-import upserts instead of duplicating.
    pat_ident = f"critcom-patient-{n:03d}"
    prac_ident = f"critcom-practitioner-{n:03d}"
    sr_ident = f"critcom-sr-{n:03d}"
    dr_ident = f"critcom-dr-{n:03d}"
    docref_ident = f"critcom-docref-{n:03d}"

    patient = {
        "resourceType": "Patient",
        "identifier": [{"system": ID_SYS, "value": pat_ident}],
        "name": [{"use": "official", "family": p["last"], "given": [p["first"]]}],
        "birthDate": p["dob"],
        "gender": p["gender"],
        "telecom": [{"system": "phone", "value": f"317-555-{4000+n:04d}", "use": "home"}],
    }

    practitioner = {
        "resourceType": "Practitioner",
        "identifier": [{"system": ID_SYS, "value": prac_ident}],
        "name": [{"use": "official", "family": p["doc_last"], "given": [p["doc_first"]]}],
        "telecom": [
            {"system": "phone", "value": p["doc_phone"], "use": "work"},
            {"system": "pager", "value": p["doc_pager"], "use": "work"},
            {"system": "email", "value": p["doc_email"], "use": "work"},
        ],
        "qualification": [
            {"code": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0360", "code": "MD"}]}}
        ],
    }

    role = {
        "resourceType": "PractitionerRole",
        "active": True,
        "practitioner": {
            "reference": prac_u,
            "display": f"Dr. {p['doc_first']} {p['doc_last']}",
        },
        "code": [
            {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "11911009",
                        "display": "Internist",
                    }
                ]
            }
        ],
        "telecom": [
            {"system": "pager", "value": p["doc_pager"], "use": "work"},
            {"system": "phone", "value": p["doc_phone"], "use": "work"},
        ],
    }

    service_request = {
        "resourceType": "ServiceRequest",
        "identifier": [{"system": ID_SYS, "value": sr_ident}],
        "status": "active",
        "intent": "order",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": p["loinc"],
                    "display": p["loinc_display"],
                }
            ],
            "text": p["study"],
        },
        "subject": {"reference": pat_u},
        "requester": {
            "reference": prac_u,
            "display": f"Dr. {p['doc_first']} {p['doc_last']}",
        },
        "reasonCode": [{"text": p["reason"]}],
        "priority": p["priority"],
    }

    # text.div — FHIR Narrative. PO's GetPatientData strips conclusion and
    # presentedForm but typically preserves text. xhtml is the canonical
    # human-readable representation.
    narrative_xhtml = (
        '<div xmlns="http://www.w3.org/1999/xhtml"><pre>'
        + p["report"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        + "</pre></div>"
    )

    diagnostic_report = {
        "resourceType": "DiagnosticReport",
        "identifier": [{"system": ID_SYS, "value": dr_ident}],
        "text": {"status": "generated", "div": narrative_xhtml},
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "RAD",
                        "display": "Radiology",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": p["loinc"],
                    "display": p["loinc_display"],
                }
            ],
            "text": p["study"],
        },
        "subject": {"reference": pat_u},
        "basedOn": [{"reference": sr_u}],
        "performer": [{"reference": prac_u}],
        "issued": NOW,
        "effectiveDateTime": NOW,
        "conclusion": p["report"],
        # presentedForm carries the same text base64-encoded. Some FHIR servers
        # (incl. some PO-managed sandboxes) drop `conclusion` if it isn't on
        # the resource's profile. fetch_report_fhir falls back to presentedForm
        # automatically, so duplicating here makes the bundle portable.
        "presentedForm": [
            {
                "contentType": "text/plain; charset=utf-8",
                "data": base64.b64encode(p["report"].encode("utf-8")).decode("ascii"),
                "title": p["study"] + " — Radiology Report",
            }
        ],
        # NOTE: No ACR extension — LLM classifier will infer the category
    }

    # DocumentReference — surfaces the report narrative through PO's
    # GetPatientDocuments tool. PO appears to use this as the canonical
    # source for free-text clinical content, so the radiology narrative
    # has to live here for PO to pass it along to CritCom.
    document_reference = {
        "resourceType": "DocumentReference",
        "identifier": [{"system": ID_SYS, "value": docref_ident}],
        "status": "current",
        "docStatus": "final",
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "18748-4",
                    "display": "Diagnostic imaging study",
                }
            ],
            "text": p["study"] + " — Radiology Report",
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/us/core/CodeSystem/us-core-documentreference-category",
                        "code": "clinical-note",
                        "display": "Clinical Note",
                    }
                ]
            }
        ],
        "subject": {"reference": pat_u},
        "date": NOW,
        "author": [{"reference": prac_u}],
        "description": p["study"] + " — finalized radiology report",
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain; charset=utf-8",
                    "data": base64.b64encode(p["report"].encode("utf-8")).decode("ascii"),
                    "title": p["study"] + " — Radiology Report",
                    "creation": NOW,
                }
            }
        ],
        "context": {
            "related": [{"reference": dr_u, "display": "Source DiagnosticReport"}],
        },
    }

    oncall_practitioner = {
        "resourceType": "Practitioner",
        "identifier": [{"system": ID_SYS, "value": "critcom-practitioner-oncall"}],
        "name": [{"use": "official", "family": "Okafor", "given": ["James"]}],
        "telecom": [
            {"system": "phone", "value": "317-555-9000", "use": "work"},
            {"system": "pager", "value": "317-555-9001", "use": "work"},
            {"system": "email", "value": "jokafor@radiology-oncall.org", "use": "work"},
        ],
    }
    oncall_role = {
        "resourceType": "PractitionerRole",
        "active": True,
        "practitioner": {
            "reference": oncall_prac_u,
            "display": "Dr. James Okafor",
        },
        "code": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0286",
                        "code": "on-call",
                        "display": "On Call",
                    }
                ]
            }
        ],
        "telecom": [
            {"system": "pager", "value": "317-555-9001", "use": "work"},
            {"system": "phone", "value": "317-555-9000", "use": "work"},
        ],
    }

    # (urn, resource, ifNoneExist-query-or-None)
    items = [
        (pat_u, patient, f"identifier={ID_SYS}|{pat_ident}"),
        (prac_u, practitioner, f"identifier={ID_SYS}|{prac_ident}"),
        (role_u, role, None),
        (oncall_prac_u, oncall_practitioner, f"identifier={ID_SYS}|critcom-practitioner-oncall"),
        (oncall_role_u, oncall_role, None),
        (sr_u, service_request, f"identifier={ID_SYS}|{sr_ident}"),
        (dr_u, diagnostic_report, f"identifier={ID_SYS}|{dr_ident}"),
        (docref_u, document_reference, f"identifier={ID_SYS}|{docref_ident}"),
    ]

    entries = []
    for urn, resource, ine in items:
        request = {"method": "POST", "url": resource["resourceType"]}
        if ine:
            request["ifNoneExist"] = ine
        entries.append({"fullUrl": urn, "resource": resource, "request": request})

    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries,
    }


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
for p in PATIENTS:
    bundle = make_bundle(p)
    fname = os.path.join(OUT_DIR, f"patient-{p['n']:03d}.json")
    with open(fname, "w") as f:
        json.dump(bundle, f, indent=2)
    expected = (
        "Cat1" if p["n"] <= 5
        else "Cat2" if p["n"] <= 8
        else "Cat3"
    )
    print(f"patient-{p['n']:03d}.json  |  {p['first']} {p['last']}  |  expected={expected}  |  {p['study']}")

print(f"\nDone — {len(PATIENTS)} bundles written to ./{OUT_DIR}/")
print("\nUpload order for demo:")
print("  Prompt 1 (discovery)   → use any patient-00[1-5].json  (Cat1)")
print("  Prompt 2 (full flow)   → same patient")
print("  Prompt 3 (escalation)  → same patient, after timeout expires")
print("\nSet CRITCOM_CAT1_ACK_TIMEOUT_MINUTES=1 before demo for fast escalation.")
