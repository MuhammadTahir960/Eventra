import {
  BalloonsIcon,
  BoxingGloveIcon,
  FootballIcon,
  GameController01Icon,
  LaughingIcon,
  MaskTheater01Icon,
  Mic01Icon,
  MusicNote01Icon,
  PaintBoardIcon,
  PartyIcon,
  Presentation01Icon,
  QuillWrite01Icon,
  Restaurant01Icon,
  Ticket01Icon,
  Wrench01Icon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

// Keys match the backend's Category.Icon choices
const ICONS = {
  music: MusicNote01Icon,
  microphone: Mic01Icon,
  laugh: LaughingIcon,
  football: FootballIcon,
  boxing: BoxingGloveIcon,
  gamepad: GameController01Icon,
  tools: Wrench01Icon,
  presentation: Presentation01Icon,
  theatre: MaskTheater01Icon,
  quill: QuillWrite01Icon,
  party: PartyIcon,
  food: Restaurant01Icon,
  palette: PaintBoardIcon,
  balloons: BalloonsIcon,
  ticket: Ticket01Icon,
}

export function CategoryIcon({ icon }: { icon: string }) {
  return (
    <HugeiconsIcon
      icon={ICONS[icon as keyof typeof ICONS] ?? Ticket01Icon}
      size={18}
      aria-hidden
    />
  )
}
