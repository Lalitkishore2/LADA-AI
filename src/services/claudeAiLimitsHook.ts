import { useEffect, useState } from 'react'
import {
  type LADAAILimits,
  currentLimits,
  statusListeners,
} from './ladaAiLimits.js'

export function useLADAAiLimits(): LADAAILimits {
  const [limits, setLimits] = useState<LADAAILimits>({ ...currentLimits })

  useEffect(() => {
    const listener = (newLimits: LADAAILimits) => {
      setLimits({ ...newLimits })
    }
    statusListeners.add(listener)

    return () => {
      statusListeners.delete(listener)
    }
  }, [])

  return limits
}

