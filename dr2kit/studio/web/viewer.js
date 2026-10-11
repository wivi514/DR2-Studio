// DR2 Studio's 3D view: a three.js orbit view of one .glb (dr2kit/convert/gltf.py).
//
// Python drives it through window.dr2 (QWebEnginePage.runJavaScript) and listens to
// console lines that start with "dr2:" (model_view.py turns them into status text).
//   dr2.load(url, keep)     show the .glb at url (Studio serves dr2://studio/model.glb);
//                           keep = true keeps the camera (a re-baked colour choice)
//   dr2.setShown(list)      variants: show part i when list[i] (the node's extras
//                           dr2_part = i, dr2kit/convert/model.py); the others hidden
//   dr2.setSkeleton(on)     bones as lines over the mesh
//   dr2.setWireframe(on)    triangles as lines
//   dr2.resetView()         frame the model again
import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from './vendor/three/examples/jsm/controls/OrbitControls.js';
import { applyLevelMaterials } from './levelmaterials.js';

const status = document.getElementById('status');
function say(text) {
  status.textContent = text;
  console.log('dr2:' + text);
}

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
} catch (e) {
  say('no WebGL here (' + e.message + '): use Export .glb… and open it in Blender');
  throw e;
}
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x2b2b2b);
scene.add(new THREE.HemisphereLight(0xffffff, 0x404040, 2.0));
const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(1, 2, 3);
scene.add(sun);
const grid = new THREE.GridHelper(4, 8, 0x555555, 0x3a3a3a);
scene.add(grid);

const camera = new THREE.PerspectiveCamera(40, window.innerWidth / window.innerHeight, 0.01, 5000);
camera.position.set(0, 1.5, 4);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1, 0);

let model = null, helper = null, wire = false, skeleton = false, meshCount = 0;
let shown = null;               // variants: which parts show (null: all)

function applyShown() {
  if (!model) return;
  model.traverse(o => {
    const i = o.userData ? o.userData.dr2_part : undefined;
    if (i !== undefined) o.visible = !shown || !!shown[i];
  });
}

function frame() {
  if (!model) return;
  const box = new THREE.Box3().setFromObject(model);
  if (box.isEmpty()) {          // a skeleton file: no geometry, so frame the bones
    model.updateMatrixWorld(true);
    model.traverse(o => { if (o.isBone) box.expandByPoint(o.getWorldPosition(new THREE.Vector3())); });
  }
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3()).length() || 1;
  const centre = box.getCenter(new THREE.Vector3());
  controls.target.copy(centre);
  // look at the front: the games' characters face +Z
  camera.position.copy(centre).add(new THREE.Vector3(0, size * 0.15, size * 1.2));
  camera.near = size / 1000;
  camera.far = size * 100;
  camera.updateProjectionMatrix();
  grid.position.y = box.min.y;
  grid.scale.setScalar(Math.max(size / 4, 0.25));
  controls.update();
}

function applyWire() {
  if (!model) return;
  model.traverse(o => {
    if (o.isMesh) for (const m of [].concat(o.material)) m.wireframe = wire;
  });
}

function applySkeleton() {
  if (helper) { scene.remove(helper); helper = null; }
  if (!model || !(skeleton || meshCount === 0)) return;   // skeleton files always show bones
  helper = new THREE.SkeletonHelper(model);
  helper.material.depthTest = false;
  scene.add(helper);
}

window.dr2 = {
  load(url, keep) {
    say('loading…');
    new GLTFLoader().load(url, async gltf => {
      await applyLevelMaterials(gltf);     // level pieces: lightmaps and blends, as the game
      if (model) scene.remove(model);
      model = gltf.scene;
      scene.add(model);
      let meshes = 0, tris = 0, bones = new Set();
      model.traverse(o => {
        if (o.isMesh) {
          meshes++;
          const g = o.geometry;
          tris += (g.index ? g.index.count : g.attributes.position.count) / 3;
          for (const m of [].concat(o.material)) m.side = THREE.DoubleSide;
        }
        if (o.isBone) bones.add(o);
      });
      meshCount = meshes;
      applyWire();
      applySkeleton();
      applyShown();
      if (!keep) frame();
      say(`${meshes} draws, ${Math.round(tris).toLocaleString()} triangles, ${bones.size} bones`);
    }, undefined, err => say('could not load the model: ' + (err.message || err)));
  },
  setShown(list) { shown = list; applyShown(); },
  setSkeleton(on) { skeleton = !!on; applySkeleton(); },
  setWireframe(on) { wire = !!on; applyWire(); },
  resetView() { frame(); },
};

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});
say('ready');
