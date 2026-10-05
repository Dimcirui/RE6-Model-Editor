# ARC class hashes of the RE6 archives

Type hash = `~crc32(class name) & 0x7FFFFFFF` (the u32 before the sizes of every archive entry). 100 distinct hashes, 153375 files.

| hash | files | class | how | ARC Studio ext | example |
|---|---|---|---|---|---|
| 241f5deb | 51697 | rTexture | MHW list (ext tex) | tex | `data/stage/s2001/scr/scr00/s0103_gunshop_BM` |
| 6d5ae854 | 20260 | rEffectList | word combination | efl | `effect/efl/stage/s2001/s200102` |
| 2749c8a8 | 10932 | rMaterial | MHW list (ext mrl3) | mrl | `data/stage/s2001/scr/scr00/s0103_yatai00` |
| 58a15856 | 10377 | rModel | MHW list (ext mod3) | mod | `data/stage/s2001/scr/scr00/s0103_yatai00` |
| 66b45610 | 10080 | rAIFSM | MHW list (ext fsm) | fsm | `soft/stage/s0000/fsm/fix/event_test` |
| 76820d81 | 5470 | rMotionList | MHW list (ext lmt) | lmt | `data/id/collect/model_cle_l` |
| 7e33a16c | 5335 | rSoundPackage | word combination | spc | `sound/se/pl/pl_cmn/snd_pl_cmn` |
| 1bcc4966 | 4986 | rSoundRequest | word combination | srq | `sound/se/em/em_cmn/snd_em_cmn` |
| 4c0db839 | 4352 | rScheduler | MHW list (ext sdl) | sdl | `data/stage/s2001/light/s2001_light` |
| 2d12e086 | 4248 | rSoundRandom | word combination | srd | `sound/se/em/em_cmn/snd_em_cmn` |
| 15302ef4 | 3524 | rLayout | word combination | lot | `data/stage/s0000/scr/scr00/s0000_m00` |
| 4e397417 | 1995 | rEffectAnim | word combination | ean | `effect/dds/etc/tx0047` |
| 39c52040 | 1981 | rCameraList | MHW list (ext lcm) | lcm | `data/id/collect/cam_cle` |
| 5fb399f4 | 1808 |  |  |  | `sound/se/scr/s0101/snd_s0101_train_jarring` |
| 167dbbff | 1560 | rSoundStreamRequest | word combination |  | `sound/bgm/snd_cmn_bgm` |
| 54dc440a | 1144 | rMotionSequenceList | word combination |  | `soft/mot_tmp/chara/em/em5000/motsoft/em5000_bha` |
| 1b520b68 | 1073 | rZone | MHW list (ext zon) |  | `sound/se/scr/s0000/snd_s0000_oc` |
| 7808ea10 | 918 | rRenderTargetTexture | MHW list (ext rtex) | rtex | `system/texture/XfEnvCube` |
| 6a9197ed | 803 |  |  |  | `sound/bgm/source/snd_str_bgm0110` |
| 296bd0a6 | 716 |  |  | hgm | `soft/chara/pl/pl0000/hit/pl00` |
| 6e45fabb | 716 | rAttackParam | MHW list (ext atk) | atk | `soft/chara/pl/pl0000/hit/pl00` |
| 12191ba1 | 704 | rEffectProvider | MHW list (ext epv3) | epv | `effect/epv/stage/s2001` |
| 4ca26828 | 669 | rSoundMotionSe | word combination | mse | `sound/se/em/em8002/snd_em8002` |
| 276de8b7 | 598 |  |  |  | `effect/e2d/0090/rt0090_08` |
| 0253f147 | 577 | rHit | word combination |  | `soft/chara/pl/pl0000/hit/pl00` |
| 65b275e5 | 536 |  |  | sce | `soft/stage/s0000/s0000_chp` |
| 51fc779f | 340 | rCollision | MHW list (ext sbc) |  | `data/stage/s0000/scr/scr00/s0000h_scr` |
| 0a4280d9 | 335 | rSoundHitData | word combination | shd | `sound/se/em/em8002/snd_em8002` |
| 535d969f | 289 | rCnsTinyChain | MHW list (ext ctc) | ctc | `data/chara/pl/pl0600/model/pl0600` |
| 266e8a91 | 270 | rLinkUnit | word combination |  | `soft/stage/s0000/s0000_lot_fsm` |
| 2282360d | 260 | rJointEx | MHW list (ext jex) | jex | `soft/chara/em/em5100/em5100` |
| 272b80ea | 224 | rPropParam | word combination | prp | `soft/stage/s0101/s0101` |
| 4ef19843 | 221 | rNavigationMesh | MHW list (ext nav) | nav | `soft/stage/s0000/s0000` |
| 1fa8b594 | 216 | rAreaHit | word combination |  | `soft/chara/em/em1000/hit/em1000` |
| 671f21da | 212 |  |  |  | `soft/stage/s0101/s0101` |
| 242bb29a | 209 | rGUIMessage | MHW list (ext gmd) |  | `soft/message/mes_system_chS` |
| 07437cce | 189 | rSoundAttributeSe | word combination | base | `sound/se/sm/snd_sm5900` |
| 039d71f2 | 173 | rSoundReverbTable | word combination |  | `sound/se/scr/s0000/snd_s0000` |
| 3b764dd4 | 167 | rSoundStreamTransition | word combination |  | `sound/bgm/scr/Menu/snd_Menu_bgm` |
| 5f36b659 | 161 | rAIWayPoint | MHW list (ext way) |  | `soft/stage/s0101/s0101_map` |
| 2a4f96a8 | 156 |  |  |  | `soft/chara/pl/pl0000/pl0000` |
| 1ed12f1b | 141 |  |  |  | `soft/stage/s0101/s0101` |
| 5802b3ff | 132 |  |  |  | `soft/stage/stage_core` |
| 285a13d9 | 132 | rFxZone | word combination |  | `effect/vzo/s0101` |
| 0026e7ff | 131 | rChainCol | MHW list (ext ccl) | ccl | `data/chara/pl/pl0000/model/pl0000` |
| 4b92d51a | 130 | rLightLinker | MHW list (ext llk) |  | `data/stage/s0101/light/s0101` |
| 35bdd173 | 125 | rPosAdjust | word combination |  | `soft/chara/pl/pl0000/hit/pl00` |
| 2c4666d1 | 116 |  |  |  | `data/stage/s0101/scr/scr00/s0101` |
| 46fb08ba | 114 |  |  |  | `data/chara/sm/sm5931/model/sm5931` |
| 4b768796 | 113 | rSoundCondition | word combination |  | `sound/se/scr/s0000/snd_s0000` |
| 6a5cdd23 | 113 |  |  |  | `data/stage/s0101/scr/scr00/s0101` |
| 25b4a6b9 | 112 |  |  |  | `sound/bgm/scr/s0101/snd_s0101` |
| 45e867d7 | 111 | rMotionListList | word combination |  | `soft/stage/s0000/s0000` |
| 15155f8a | 107 |  |  |  | `data/stage/s0101/scr/scr00/s0101` |
| 02833703 | 92 |  |  |  | `effect/efs/es0001` |
| 5175c242 | 92 | rGeometry2 | MHW list (ext geo2) |  | `soft/chara/sm/sm1001/hit/sm1001` |
| 1eb3767c | 91 |  |  |  | `sound/se/em/em5000/snd_em5000_body` |
| 6fe1ea15 | 91 |  |  |  | `sound/se/em/em5000/snd_em5000_body` |
| 257d2f7c | 85 |  |  |  | `data/stage/s0201/scr/scr00/s0201_wood` |
| 33046cd5 | 85 |  |  |  | `soft/chara/pl/pl0000/pl0000` |
| 622fa3c9 | 84 |  |  |  | `soft/stage/s0101/s0101_npc` |
| 601e64cd | 73 | rSoundZoneSwitch | word combination |  | `sound/se/scr/s0102/snd_s0102` |
| 45f753e8 | 69 |  |  |  | `sound/se/scr/s0102/snd_s0102` |
| 0437bcf2 | 67 | rGrassWind | word combination | grw | `effect/grw/gw0002` |
| 1aadf7b7 | 65 |  |  |  | `soft/chara/pl/pl0000/pl0000` |
| 3b5c7fd3 | 62 |  |  |  | `soft/id/jpn/collect/collect` |
| 58819bc8 | 51 |  |  |  | `sound/se/scr/s0000/snd_s0000` |
| 14ea8095 | 37 | rCnsOffsetSet | word combination |  | `soft/chara/pl/pl0000/base` |
| 54e2d1ff | 32 | rPadData | word combination |  | `soft/chara/em/em7400/PadData/padData00` |
| 7d1530c2 | 26 | rSoundSourceMusic | word combination |  | `sound/bgm/source/bgm1117` |
| 2f4e7041 | 26 |  |  |  | `sound/se/wp/snd_wp1010` |
| 4323d83a | 24 | rSceneTexture | MHW list (ext stex) |  | `data/event/image/m_512x512` |
| 31edc625 | 20 |  |  |  | `sound/se/em/em5000/snd_em5000_body` |
| 25fa21cb | 20 | rAIWayPointGraph | MHW list (ext gway) |  | `soft/stage/s1300/s1300` |
| 62a68441 | 17 | rThinkTable | MHW list (ext thk) |  | `soft/chara/em/em3000/em3000` |
| 2d462600 | 16 | rGUIFont | MHW list (ext gfd) |  | `soft/message/font/mes_font` |
| 30fc745f | 14 |  |  |  | `sound/preset/smx/snd_init_0000` |
| 538120de | 13 |  |  |  | `sound/se/sm/snd_sm1262_r0` |
| 19f6efce | 11 | rSoundEnemyParam | word combination |  | `sound/se/scr/s0101/snd_s0101` |
| 52dbdcd6 | 8 |  |  |  | `soft/chara/em/em1000/em1000` |
| 46810940 | 7 |  |  |  | `sound/se/sm/snd_sm1262` |
| 628dfb41 | 6 |  |  |  | `data/stage/s0102/scr/scr00/s0102red` |
| 11c35522 | 5 |  |  |  | `data/stage/s0102/scr/scr00/s0102` |
| 49b5a885 | 4 |  |  |  | `sound/preset/smx/snd_fader_curve00` |
| 69a5c538 | 4 |  |  |  | `data/chara/em/em2210/model/em2210` |
| 22948394 | 2 | rGUI | MHW list (ext gui) |  | `soft/message/gui/mes` |
| 2c2de8ca | 2 |  |  |  | `effect/adh/fm` |
| 245133d9 | 2 | rCameraRail | word combination |  | `soft/stage/s0804/s0804_00` |
| 02a80e1f | 2 |  |  |  | `soft/chara/em/em2100/kama_left` |
| 7bec319a | 2 |  |  |  | `sound/se/sm/snd_sm1293` |
| 0ecd7df4 | 1 | rSoundCurveSet | word combination |  | `sound/preset/snd_bh6_scs` |
| 0315e81f | 1 |  |  |  | `sound/preset/snd_bh6_sds` |
| 232e228c | 1 | rSoundReverb | word combination |  | `sound/preset/snd_bh6_rev` |
| 2b40ae8f | 1 |  |  |  | `sound/preset/snd_bh6_eq` |
| 07f768af | 1 | rGUIIconInfo | MHW list (ext gii) |  | `soft/message/font/mes_icon` |
| 358012e8 | 1 | rVibration | MHW list (ext vib) |  | `etc/bh6_vibration` |
| 6bb4ed5e | 1 | rLch | MHW list (ext lch) |  | `etc/lightChr` |
| 2739b57c | 1 | rGrass | word combination |  | `data/stage/s0000/scr/scr00/grass` |
| 56cf93d4 | 1 |  |  |  | `soft/stage/s0514/s0514h_scr` |
| 4e2fef36 | 1 |  |  |  | `data/chara/em/em9020/model/em9020` |

Unresolved: 41 hashes, 6556 files.
