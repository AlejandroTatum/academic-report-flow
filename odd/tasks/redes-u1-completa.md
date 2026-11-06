# Redes U1 complete study guide (M1-M17)
One study guide for Fundamentos de Redes Unit 1, Cisco "Conceptos básicos de redes" modules 1-17, built with the metro-topologia guide theme.
Destination: ~/Documents/Universidad/Ciclo-5/fundamentos-de-redes/estudio/u1-completa/ (outline.txt approved at gate 1).

## Specs
- S1: "hagamos un solo doc con la u1 del modulo 1 al 17, que incluya todo"
- S2: Same look as the video deck (metro-topologia theme, layer colors app violet, transport amber, internet blue, access green).
- S3: Recording block included, "nada de guion": keywords, what to master and self-check questions only, no script phrases.
- S4: Follows the approved outline: parts 0-7, about 58 pages, checkpoint banks for M1-M4, M5-M7 and M8-M10, final quiz of 20 questions with reasoned answers.
- S5: Existing guides (modulos-11-17, hola-mundo-capas, viaje-del-paquete) stay untouched.
- S6: Checker passes (render.sh + check_deck.py --mode guide --dom); gate 2 stays open for the user.

## Tasks
- [x] T1 S2,S5 Scaffold folder, theme, fonts, components, cover, map, how to study | done, see Log | n/a
- [x] T2 S1,S4 Part 1: networks and devices (M1-M4, LAN/WAN, checkpoint 1) | done, see Log | n/a
- [x] T3 S1,S4 Part 2: rules and models (standards, M5, OSI, TCP/IP, encapsulation) | done, see Log | n/a
- [x] T4 S1,S4 Part 3: access (M6, M7, switch, checkpoint 2) | done, see Log | n/a
- [x] T5 S1,S4 Part 4: addressing (M8-M10, binary, checkpoint 3) | done, see Log | n/a
- [x] T6 S1,S3 Parts 5-6: reuse M11-M17, diagnosis, pairs, terminal, Packet Tracer, recording block | done, see Log | n/a
- [x] T7 S4 Part 7: orals, banks, exercises, memory sheet, quiz 20 + answers | done, see Log | n/a
- [x] T8 S6 Render, check, visual review, open PDF | done, see Log | n/a

## Log
- L1: "hagamos un solo doc con la u1 del modulo 1 al 17, que incluya todo"
- L2: Earlier in session: "si nada de guion, aparte de esta guia, quisiera otro documento para reforzar conceptos"; outline approved with "si".
- L3: Decision: OSI/TCP-IP/encapsulation pages reused from hola-mundo-capas (12 pages) instead of rewritten; guide grew from ~58 to 72 pages. Checkpoint pages cp1-cp3 are labelled own practice because the source has no official M1-M7 checkpoint questions; real final-exam items stay in banco-6/7.
- L4: Writers W1 (p0-p2, 12 pages) and W2 (p3, p4, p7, 17 pages) done; full build 72 pages, check_deck --outline passes (count, anchors, fonts, font-size, overflow). Fact-check running.
- L5: Fact-check: 1 confirmed error fixed (cp2 "cuatro reglas" → five rules incl. delivery options); also IETF name, Bluetooth 1-100 m, MAN = city, memoria router +firewall. Final build 72 pages, all checks pass, PDF opened. Gate 2 open. Sources copied to u1-completa/_fuente/.
