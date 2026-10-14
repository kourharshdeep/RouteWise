
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { fetchCorridorPlaces, planJourney } from '../services/api';

const JourneyContext = createContext(null);

export function JourneyProvider({ children }) {
  const [vehicleType, setVehicleType] = useState(
    () => localStorage.getItem('routewise_vehicle') || 'Car'
  );
  const [origin, setOrigin] = useState('Ramban');
  const [destination, setDestination] = useState('Banihal');
  const [journeyDate, setJourneyDate] = useState('2023-07-09');
  const [departureTime, setDepartureTime] = useState('08:00');
  const [arrivalDeadline, setArrivalDeadline] = useState('');
  
  const [places, setPlaces] = useState([]);
  const [planResult, setPlanResult] = useState(null);
  const [isPlanning, setIsPlanning] = useState(false);
  const [planError, setPlanError] = useState(null);

  // Sync vehicle type to localStorage
  useEffect(() => {
    localStorage.setItem('routewise_vehicle', vehicleType);
  }, [vehicleType]);

  // Load corridor landmark places on mount
  useEffect(() => {
    async function loadPlaces() {
      try {
        const data = await fetchCorridorPlaces();
        setPlaces(data);
      } catch (err) {
        console.warn('Failed to load corridor places:', err);
      }
    }
    loadPlaces();
  }, []);

  const executePlan = useCallback(
    async (overrideParams = {}) => {
      const payload = {
        origin: overrideParams.origin || origin,
        destination: overrideParams.destination || destination,
        date: overrideParams.date || journeyDate,
        departure_time: overrideParams.departureTime || departureTime,
        arrival_deadline: overrideParams.arrivalDeadline !== undefined ? overrideParams.arrivalDeadline : (arrivalDeadline || null),
        vehicle_type: overrideParams.vehicleType || vehicleType,
      };

      try {
        setIsPlanning(true);
        setPlanError(null);
        const result = await planJourney(payload);
        setPlanResult(result);
        return result;
      } catch (err) {
        console.error('Plan journey error:', err);
        setPlanError(err.message || 'Failed to analyze journey');
        throw err;
      } finally {
        setIsPlanning(false);
      }
    },
    [origin, destination, journeyDate, departureTime, arrivalDeadline, vehicleType]
  );

  const resetJourney = useCallback(() => {
    setPlanResult(null);
    setPlanError(null);
    setOrigin('Ramban');
    setDestination('Banihal');
    setJourneyDate('2023-07-09');
    setDepartureTime('08:00');
    setArrivalDeadline('');
  }, []);

  return (
    <JourneyContext.Provider
      value={{
        vehicleType,
        setVehicleType,
        origin,
        setOrigin,
        destination,
        setDestination,
        journeyDate,
        setJourneyDate,
        departureTime,
        setDepartureTime,
        arrivalDeadline,
        setArrivalDeadline,
        places,
        planResult,
        setPlanResult,
        isPlanning,
        planError,
        executePlan,
        resetJourney,
      }}
    >
      {children}
    </JourneyContext.Provider>
  );
}

export function useJourney() {
  const context = useContext(JourneyContext);
  if (!context) {
    throw new Error('useJourney must be used within a JourneyProvider');
  }
  return context;
}
