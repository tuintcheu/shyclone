/* Le logo est fourni en PNG noir sur fond transparent (public/logo.png,
   dérivé de screen.png). `dark:invert` suffit donc à le passer en blanc sur
   le thème sombre, sans seconde image à maintenir. */

export function Logo({ className = '' }) {
  return (
    <img
      src="/logo.png"
      alt="ShyClone"
      width={770}
      height={290}
      className={`w-auto select-none dark:invert ${className}`}
      draggable={false}
    />
  )
}

export function Mark({ className = '' }) {
  return (
    <img
      src="/mark.png"
      alt=""
      aria-hidden="true"
      width={183}
      height={290}
      className={`w-auto select-none dark:invert ${className}`}
      draggable={false}
    />
  )
}
