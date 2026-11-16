import * as THREE from 'three';
import {blinkAt, mouthAt} from './scene_logic.mjs';

export function createRoom(canvas) {
  const renderer = new THREE.WebGLRenderer({canvas, antialias: true, preserveDrawingBuffer: true});
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0xdce6df);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0xdce6df, 14, 24);
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 40);
  scene.add(new THREE.HemisphereLight(0xfffcf0, 0x9cae9c, 2.8));
  const sun = new THREE.DirectionalLight(0xffe6c6, 3.2);
  sun.position.set(-3, 7, 5);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, {left: -7, right: 7, top: 7, bottom: -7});
  sun.shadow.bias = -0.001;
  scene.add(sun);
  const materials = new Map();
  function material(color) {
    if (!materials.has(color)) materials.set(color, new THREE.MeshStandardMaterial({color, roughness: 0.85}));
    return materials.get(color);
  }
  function shape(geometry, color, parent, x = 0, y = 0, z = 0) {
    const mesh = new THREE.Mesh(geometry, material(color));
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }
  function box(parent, color, x, y, z, w, h, d) {
    return shape(new THREE.BoxGeometry(w, h, d), color, parent, x, y, z);
  }
  function oval(parent, color, x, y, z, w, h, d) {
    const mesh = shape(new THREE.SphereGeometry(1, 24, 16), color, parent, x, y, z);
    mesh.scale.set(w, h, d);
    return mesh;
  }
  function rod(parent, color, x, y, z, r, h) {
    return shape(new THREE.CylinderGeometry(r, r, h, 16), color, parent, x, y, z);
  }
  box(scene, 0xd5dfcf, 0, -0.11, 0, 16, 0.2, 14);
  box(scene, 0xe9e9dc, 0, 2.3, -3.2, 15, 4.8, 0.15);
  box(scene, 0xc3d3c3, -5, 2.2, 0, 0.1, 4.5, 7);
  box(scene, 0xb8c9bc, 0.5, 0.015, 0.25, 6.3, 0.025, 4.6);
  for (let i = 0; i < 5; i++) {
    box(scene, 0x9db6a4, -4.92, 0.6 + i * 0.7, -0.2, 0.04, 0.025, 5.3);
  }
  // Abstract wall art keeps the scene self-contained and avoids model assets.
  box(scene, 0xa58466, -1.5, 2.7, -3.08, 1.6, 1.1, 0.07);
  box(scene, 0xf8f2df, -1.5, 2.7, -3.025, 1.47, 0.97, 0.03);
  oval(scene, 0xc28b60, -1.65, 2.85, -2.99, 0.27, 0.27, 0.02);
  box(scene, 0x91aa91, -1.25, 2.52, -2.97, 0.82, 0.23, 0.03);
  box(scene, 0xe0c5a1, 0, 0.98, 0.05, 3.15, 0.13, 1.7);
  for (const x of [-1.22, 1.22]) for (const z of [-0.56, 0.64]) {
    box(scene, 0x6a8071, x, 0.47, z, 0.09, 0.94, 0.09);
  }
  box(scene, 0xf9f4e8, -0.75, 1.06, 0.1, 0.55, 0.018, 0.38).rotation.y = -0.12;
  box(scene, 0xf9f4e8, 0.85, 1.06, 0.1, 0.55, 0.018, 0.38).rotation.y = 0.16;
  box(scene, 0x415b59, 0.87, 1.08, 0.08, 0.025, 0.025, 0.3).rotation.y = 0.25;
  rod(scene, 0xd8b38f, 0.2, 1.17, -0.15, 0.09, 0.25);
  rod(scene, 0x587063, 3.1, 0.37, -2, 0.31, 0.7);
  rod(scene, 0x6d7950, 3.1, 1.1, -2, 0.04, 1.4);
  for (let i = 0; i < 7; i++) {
    const a = i * 2.4;
    const leaf = oval(scene, i % 2 ? 0x829c69 : 0x617f55,
      3.1 + Math.cos(a) * 0.25, 1.1 + i * 0.12, -2 + Math.sin(a) * 0.2, 0.18, 0.38, 0.09);
    leaf.rotation.z = Math.cos(a) * 0.7;
  }
  function person({id, x, z, angle, skin, hair, shirt, longHair, glasses, offset}) {
    const root = new THREE.Group();
    root.position.set(x, 0, z);
    root.rotation.y = angle;
    scene.add(root);
    box(root, 0x6c8578, 0, 0.54, 0, 0.85, 0.15, 0.7);
    box(root, 0x6c8578, 0, 0.98, -0.3, 0.84, 0.85, 0.12);
    for (const side of [-1, 1]) {
      box(root, 0x68716a, side * 0.31, 0.25, 0, 0.055, 0.5, 0.055);
      box(root, 0x435361, side * 0.2, 0.42, 0.25, 0.23, 0.75, 0.27);
      oval(root, 0x4a4b43, side * 0.2, 0.1, 0.38, 0.15, 0.09, 0.24);
    }
    const body = new THREE.Group();
    body.position.y = 0.65;
    root.add(body);
    oval(body, shirt, 0, 0.55, 0, 0.43, 0.56, 0.26);
    rod(body, skin, 0, 1.04, 0, 0.12, 0.25);
    const head = new THREE.Group();
    head.position.set(0, 1.35, 0.03);
    body.add(head);
    if (longHair) oval(head, hair, 0, -0.08, -0.13, 0.35, 0.48, 0.24);
    oval(head, skin, 0, 0, 0, 0.29, 0.36, 0.255);
    oval(head, hair, 0, 0.21, -0.07, 0.305, 0.22, 0.24);
    oval(head, hair, -0.17, 0.21, 0.1, 0.14, 0.16, 0.15);
    for (const side of [-1, 1]) {
      oval(head, skin, side * 0.285, -0.03, 0, 0.055, 0.085, 0.05);
      oval(head, 0xe0a68d, side * 0.15, -0.12, 0.214, 0.065, 0.035, 0.018);
    }
    const eyes = [-1, 1].map(side => {
      const eye = oval(head, 0x343b37, side * 0.105, 0.025, 0.24, 0.029, 0.042, 0.021);
      box(head, hair, side * 0.105, 0.11, 0.228, 0.085, 0.018, 0.024);
      return eye;
    });
    oval(head, skin, 0, -0.04, 0.26, 0.042, 0.065, 0.045);
    const mouth = oval(head, 0x734e47, 0, -0.17, 0.229, 0.058, 0.012, 0.016);
    if (glasses) {
      const lineMaterial = new THREE.MeshStandardMaterial({color: 0x5c4c40, roughness: 0.7});
      for (const side of [-1, 1]) {
        const rim = new THREE.Mesh(new THREE.TorusGeometry(0.073, 0.008, 8, 24), lineMaterial);
        rim.position.set(side * 0.105, 0.025, 0.263);
        head.add(rim);
      }
      box(head, 0x5c4c40, 0, 0.035, 0.269, 0.065, 0.01, 0.01);
    }
    const arms = [-1, 1].map(side => {
      const arm = new THREE.Group();
      arm.position.set(side * 0.37, 0.88, 0);
      arm.rotation.z = side * 0.14;
      body.add(arm);
      oval(arm, shirt, 0, -0.2, 0.015, 0.115, 0.29, 0.12);
      oval(arm, skin, 0, -0.4, 0.17, 0.09, 0.1, 0.19);
      return arm;
    });
    return {id, root, body, head, mouth, eyes, arms, offset};
  }
  const actors = [
    person({id: 'candidate', x: -2, z: 0.25, angle: 1.08, skin: 0xd7a179, hair: 0x4e3e32, shirt: 0xb87c58, longHair: true, offset: 0.7}),
    person({id: 'examiner', x: 2, z: 0.25, angle: -1.08, skin: 0xe0b28f, hair: 0x665c50, shirt: 0x4e7778, glasses: true, offset: 2.1}),
    person({id: 'observer', x: 0.65, z: -1.65, angle: -0.1, skin: 0xc68b69, hair: 0x383c37, shirt: 0x8e9382, longHair: true, glasses: true, offset: 3.4}),
  ];
  function draw(time, turn) {
    const bounds = canvas.getBoundingClientRect();
    if (canvas.width !== Math.round(bounds.width) || canvas.height !== Math.round(bounds.height)) {
      renderer.setSize(Math.round(bounds.width), Math.round(bounds.height), false);
      camera.aspect = bounds.width / bounds.height;
      camera.updateProjectionMatrix();
    }
    const portrait = bounds.width / bounds.height < 1.6;
    camera.position.set(0.12 * Math.sin(time * 0.12), portrait ? 4.5 : 4.15, portrait ? 9.5 : 8.8);
    camera.lookAt(0, 1.15, -0.05);
    for (const actor of actors) {
      const speaking = turn?.speaker === actor.id;
      const opening = speaking ? mouthAt(turn, time) : 0;
      actor.mouth.scale.y = 0.012 + opening * 0.075;
      actor.mouth.scale.x = 0.058 + opening * 0.016;
      actor.body.rotation.z = 0.007 * Math.sin(time * 1.4 + actor.offset);
      actor.head.rotation.x = speaking ? 0.025 * Math.sin(time * 4.4) : 0.008 * Math.sin(time * 1.9 + actor.offset);
      actor.head.rotation.y = 0.04 * Math.sin(time * 0.8 + actor.offset);
      actor.eyes.forEach(eye => { eye.scale.y = 0.042 * blinkAt(time, actor.offset); });
      actor.arms[0].rotation.x = speaking ? -0.1 - opening * 0.2 : 0;
      actor.arms[1].rotation.x = 0;
    }
    renderer.render(scene, camera);
    return {
      triangles: renderer.info.render.triangles,
      geometries: renderer.info.memory.geometries,
      mouths: Object.fromEntries(actors.map(actor => [actor.id, actor.mouth.scale.y])),
      heads: actors.map(actor => {
        const p = actor.head.getWorldPosition(new THREE.Vector3()).project(camera);
        return {id: actor.id, x: (p.x + 1) / 2, y: (1 - p.y) / 2, z: p.z};
      }),
    };
  }
  return {draw, renderer};
}
