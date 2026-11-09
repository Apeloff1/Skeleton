"""URDF/SDF/MJCF static articulated graphs, finite physics fields, replay."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.urdf_documents import extract_urdf
from skeleton.ai.webcrawler.sdf_documents import extract_sdf
from skeleton.ai.webcrawler.mjcf_documents import extract_mjcf
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun

URDF='''<?xml version="1.0"?>
<robot name="OriginalAirframe">
  <link name="base_link">
    <visual><geometry><mesh filename="https://outside.example.net/SECRET_MESH"/></geometry></visual>
    <collision><geometry><box size="1 2 3"/></geometry></collision>
    <inertial><mass value="2.5"/></inertial>
  </link>
  <link name="wing"/>
  <link name="thruster"/>
  <joint name="flight_joint" type="revolute">
    <parent link="base_link"/><child link="wing"/>
    <limit lower="-1.5" upper="1.5" velocity="12" effort="100"/>
  </joint>
  <joint name="thruster_joint" type="fixed">
    <parent link="wing"/><child link="thruster"/>
  </joint>
</robot>
'''
SDF='''<?xml version="1.0"?>
<sdf version="1.9">
  <model name="OriginalFlight">
    <link name="base">
      <visual name="geometry"><geometry><mesh><uri>https://outside.example.net/PRIVATE</uri></mesh></geometry></visual>
      <collision name="solid"><geometry><box/></geometry></collision>
      <inertial><mass>4.5</mass></inertial>
    </link>
    <link name="wing"/>
    <link name="tail"/>
    <joint name="wing_joint" type="revolute">
      <parent>base</parent><child>wing</child>
    </joint>
    <joint name="tail_joint" type="fixed">
      <parent>wing</parent><child>tail</child>
    </joint>
    <include><uri>model://PRIVATE_ASSET</uri></include>
  </model>
</sdf>
'''
MJCF='''<?xml version="1.0"?>
<mujoco model="OriginalFlight">
<asset><mesh name="PrivateWingMesh" file="https://outside.example.net/SECRET_MESH"/></asset>
<worldbody>
  <body name="airframe">
    <joint name="base_joint" type="hinge" range="-1.2 1.2"/>
    <geom type="box" size="1 2 3"/>
    <body name="wing">
      <joint name="wing_hinge" type="hinge" range="-1 1"/>
      <geom type="mesh" mesh="PrivateWingMesh"/>
      <body name="thruster"><site name="thrust_point"/></body>
    </body>
    <body name="camera"><camera name="Pilot"/></body>
  </body>
</worldbody>
<include file="../../PRIVATE_PLUGIN.xml"/>
</mujoco>
'''

class URDFContractTests(unittest.TestCase):
    def test_links_joints_depth_and_external_mesh_omission(self):
        row=extract_urdf(URDF)
        self.assertIn("Links: 3; joints: 2",row.text)
        self.assertIn("Hierarchy depth: 2",row.text)
        self.assertIn("revolute=1",row.text)
        self.assertIn("fixed=1",row.text)
        self.assertIn("mesh refs: 1",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertNotIn("SECRET_MESH",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_missing_link_fails_closed(self):
        bad=URDF.replace('child link="thruster"','child link="missing"')
        with self.assertRaises(ResearchFormatError):
            extract_urdf(bad)

    def test_cycle_and_duplicate_parent_rejected(self):
        cycle=URDF.replace('<parent link="wing"/><child link="thruster"/>',
                           '<parent link="wing"/><child link="base_link"/>')
        with self.assertRaises(ResearchFormatError):
            extract_urdf(cycle)
        ambig=URDF.replace('child link="thruster"','child link="wing"')
        with self.assertRaises(ResearchFormatError):
            extract_urdf(ambig)

    def test_nonfinite_joint_limit_and_mass_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_urdf(URDF.replace('velocity="12"','velocity="NaN"'))
        with self.assertRaises(ResearchFormatError):
            extract_urdf(URDF.replace('mass value="2.5"','mass value="-1"'))

    def test_xml_entity_expansion_refused(self):
        with self.assertRaises(ResearchFormatError):
            extract_urdf('<!DOCTYPE robot [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+URDF)

    def test_unsupported_robot_macro_namespace_not_instantiated(self):
        source=URDF.replace('<robot name="OriginalAirframe">',
            '<robot xmlns:xacro="http://ros.org/wiki/xacro" name="OriginalAirframe">'
            '<xacro:include filename="../../private.xacro"/>')
        row=extract_urdf(source)
        self.assertIn("Links: 3",row.text)
        self.assertEqual(row.links,())

class SDFContractTests(unittest.TestCase):
    def test_model_articulation_and_inert_include(self):
        row=extract_sdf(SDF)
        self.assertIn("SDF version: 1.9; articulated links: 3",row.text)
        self.assertIn("Joint declarations: 2",row.text)
        self.assertIn("Hierarchy depth: 2",row.text)
        self.assertIn("External includes declared but not loaded: 1",row.text)
        self.assertNotIn("PRIVATE_ASSET",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())

    def test_missing_model_or_parent_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_sdf('<sdf version="1.9"></sdf>')
        with self.assertRaises(ResearchFormatError):
            extract_sdf(SDF.replace('<parent>base</parent>','<parent>UNKNOWN</parent>'))

    def test_invalid_or_nonfinite_mass_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_sdf(SDF.replace('version="1.9"','version="999.0"'))
        with self.assertRaises(ResearchFormatError):
            extract_sdf(SDF.replace('<mass>4.5</mass>','<mass>Infinity</mass>'))

    def test_duplicate_link_and_joint_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_sdf(SDF.replace('<link name="tail"/>','<link name="wing"/>'))

class MJCFContractTests(unittest.TestCase):
    def test_body_tree_joint_geoms_no_include_loading(self):
        row=extract_mjcf(MJCF)
        self.assertIn("Declared bodies: 4; joints: 2",row.text)
        self.assertIn("Hierarchy depth: 2",row.text)
        self.assertIn("Geom objects: 2",row.text)
        self.assertIn("Mesh asset declarations: 1; includes: 1",row.text)
        self.assertNotIn("SECRET_MESH",row.text)
        self.assertNotIn("PRIVATE_PLUGIN",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.reference_trusted)

    def test_duplicate_sibling_body_rejected(self):
        bad=MJCF.replace('<body name="camera">','<body name="wing">')
        with self.assertRaises(ResearchFormatError):
            extract_mjcf(bad)

    def test_nonfinite_joint_range_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_mjcf(MJCF.replace('range="-1 1"','range="0 NaN"'))

    def test_body_depth_limit(self):
        nested='<mujoco><worldbody>'+('<body name="Level">'*35)
        nested+=("</body>"*35)+'</worldbody></mujoco>'
        with self.assertRaises(ResearchFormatError):
            extract_mjcf(nested)

    def test_no_worldbody_or_body_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_mjcf('<mujoco/>')
        with self.assertRaises(ResearchFormatError):
            extract_mjcf('<mujoco><worldbody/></mujoco>')

class Transport:
    timeout_seconds=4
    transport_mode="scripted_articulated_scene"
    def __init__(self,mime,text):
        self.mime,self.body,self.calls=mime,text.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/robot":
            raise AssertionError("robot source attempted external mesh/plugin IO")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())

class CanonicalRobotSourceTests(unittest.TestCase):
    def test_robotics_sources_enter_canonical_unreviewed_custody(self):
        for mime,raw,marker in (
            ("model/urdf+xml",URDF,"Links: 3; joints: 2"),
            ("model/sdf+xml",SDF,"Joint declarations: 2"),
            ("application/x-mjcf+xml",MJCF,"Declared bodies: 4"),
        ):
            with self.subTest(mime=mime):
                now=time.time()
                fetcher=Transport(mime,raw)
                run=CrawlRun.create(
                    CrawlRequest(seed_urls=("https://example.com/robot",),
                        allowed_hosts=("example.com",),max_depth=1,
                        max_requests=4,max_documents=2,
                        max_response_bytes=65536,max_total_bytes=131072),
                    scope={"tenant_id":"t","owner_id":"o"},
                    consent={"consent_id":"robotics-source-rights",
                             "capture_acknowledged":True,
                             "source_rights_acknowledged":True,
                             "expires_at":now+3600},
                    now=now,fetcher=fetcher)
                for offset in (1,3):
                    with patch("skeleton.ai.webcrawler.operations.time.time",
                               return_value=now+offset):
                        run.run_slice(max_steps=1,max_seconds=1,
                            authorize=lambda:None,cancelled=lambda:False,
                            on_checkpoint=lambda snap,event:None)
                state=run.snapshot()
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                record=run.sources()[0]
                self.assertIn(marker,record["text"])
                self.assertIn("Scene topology SHA256:",record["text"])
                self.assertEqual(record["review_state"],"unreviewed")
                self.assertFalse(record["provenance"]["training_permission"])
                self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

    def test_media_allowlist_explicit(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("model/urdf+xml","model/sdf+xml","application/x-mjcf+xml"):
            self.assertIn(mime,allowed)
        self.assertNotIn("application/x-msdownload",allowed)

if __name__=="__main__":
    unittest.main()
