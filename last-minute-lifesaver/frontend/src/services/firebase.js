/**
 * Firebase client SDK init. Fill in your config from the Firebase console
 * (Project settings > General > Your apps > Web app).
 */
import { initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

const firebaseConfig = {
  apiKey: "AIzaSyCJmJRoVzzqMWqJYo-azpnEm56LPQCW-r0",
  authDomain: "lastminlifesaver.firebaseapp.com",
  projectId: "lastminlifesaver",
  storageBucket: "lastminlifesaver.firebasestorage.app",
  messagingSenderId: "178863056027",
  appId: "1:178863056027:web:aeb20462839b544194d23e",
  measurementId: "G-JWE208W1GE"
}

export const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
