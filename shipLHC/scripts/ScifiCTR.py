import shipunit as u
import rootUtils as ut
import ROOT
import ctypes
import pickle
from array import array

A,B=ROOT.TVector3(),ROOT.TVector3()

def FCN(npar, gin, f, par, iflag):
#calculate chisquare
       chisq  = 0
       X = ROOT.gROOT.FindObjectAny('commonBlock')
       for matH in range(3):
            for matV in range(3):
               tdiff = X.GetBinContent(matH*10+matV)
               d = tdiff - (par[matH] - par[matV+3])
               chisq += d**2
       f.value = chisq
       return

def FCNS(npar, gin, f, par, iflag):
#calculate chisquare
       chisq  = 0
       X = ROOT.gROOT.FindObjectAny('commonBlock')
       for s1 in range(1,6): 
          for s2 in range(s1+1,6): 
             tdiff = X.GetBinContent(s1*10+s2)
             d = tdiff - (par[s2-1] - par[s1-1])
             chisq += d**2
       f.value = chisq
       return

class Scifi_CTR(ROOT.FairTask):
   " time resolution comparing X/Y in same station"
   def Init(self,monitor):
       self.M = monitor
       h = self.M.h
       self.projs = {1:'V',0:'H'}

       self.tag = monitor.iteration
       tag = self.tag
       for s in range(1,6):
               ut.bookHist(h,'CTR_Scifi'+str(s)+tag,'CTR '+str(s)+tag+'; dt [ns]; ',100,-5.,5.)
               ut.bookHist(h,'CTR_Scifi_beam'+str(s)+tag,'CTR beam'+str(s)+tag+'; dt [ns]; ',100,-5.,5.)
               for matH in range(3):
                   for matV in range(3):
                    ut.bookHist(h,'CTR_Scifi'+str(s*100+10*matH+matV)+tag,'CTR '+str(s)+tag+'; dt [ns]; ',100,-5.,5.)
                    ut.bookHist(h,'CTR_Scifi_beam'+str(s*100+10*matH+matV)+tag,'CTR beam'+str(s)+tag+'; dt [ns]; ',100,-5.,5.)

               for p in self.projs:
                    ut.bookHist(h,'res'+str(s)+self.projs[p],'d;  [cm]; ',100,-1.,1.)
                    ut.bookHist(h,'resX'+str(s)+self.projs[p],'d;  [cm]; ',100,-1.,1.)
                    ut.bookHist(h,'extrap'+str(s)+self.projs[p],'SiPM distance; L [cm]; ',100,0.,50.)

       for s1 in range(1,5):
           for s2 in range(s1+1,6):
              ut.bookHist(h,'CTR_ScifiStation'+str(s1*10+s2)+tag,'CTR station'+str(s1*10+s2)+'; dt [ns]; ',100,-5.,5.)
              ut.bookHist(h,'CTR_ScifiStation_beam'+str(s1*10+s2)+tag,'CTR station beam'+str(s1*10+s2)+'; dt [ns]; ',100,-5.,5.)

       if self.tag == "v0":
           self.tdcScifiStationCalib = {}
           for s in range(1,6):
                self.tdcScifiStationCalib[s] = [0,{'H':{0:0,1:0,2:0},'V':{0:0,1:0,2:0}}]

       else:
            with open('ScifiTimeAlignment_'+self.tag, 'rb') as fh:
               self.tdcScifiStationCalib = pickle.load(fh)

       self.V = 15 * u.cm/u.ns
       self.C = 299792458 * u.m/u.s

   def ExecuteEvent(self,event):

       # Set monitoring 
       h = self.M.h
       tag =  self.tag

       # Mapping between detector HitID and key
       DetID2Key={}
       for nHit in range(event.Digi_ScifiHits.GetEntries()):
           # index by nHit 
           DetID2Key[event.Digi_ScifiHits[nHit].GetDetectorID()] = nHit


       # Loop over tracks 
       for aTrack in event.Reco_MuonTracks:
          
          # Skip non-Unique ID 
          if not aTrack.GetUniqueID()==1: continue

          # Skip non-coverage track 
          fitStatus = aTrack.getFitStatus()
          if not fitStatus.isFitConverged(): continue
          
          # Get Fit state, momentum and positions
          state = aTrack.getFittedState()
          mom = state.getMom()
          slopeX = mom.X()/mom.Z()
          slopeY = mom.Y()/mom.Z()


          # Payload for clusters 
          sortedClusters={}
          for s in range(1,6):  sortedClusters[s] = {'H':[],'V':[]}

          # Loop over all clusters on Tracks 
          ## Add to sortedClusters payload 
          for nM in range(aTrack.getNumPointsWithMeasurement()):

              # Get fitted state  
              state = aTrack.getFittedState(nM) # state 
              Meas = aTrack.getPointWithMeasurement(nM) # 

              # Check only the fastest HIT in the cluster 
              W     = Meas.getRawMeasurement()
              clkey = W.getHitId()  # HitID 
              aCl   = event.Cluster_Scifi[clkey] # Cluster 
              aHit = event.Digi_ScifiHits[DetID2Key[aCl.GetFirst()]] # First fastest hit in a cluster
              s = aCl.GetFirst()//1000000  # Station 
              aCl.GetPosition(A,B)
              mat = (aCl.GetFirst()//10000)%10 # Mat 

              # Check vertical and horizontal 
              ## sortedClusters[STATION][ORIENTATION][INDEX_SORTED_CLUSTERS]
              ###                 payload: [FASTEST_HITID, LENGTH_POS, RIGHT_POS_CLUS, Y_POSITION, MAT_NUMBER, Z_POSITION]
              if aHit.isVertical(): 
                        # Vertical 
                        L = B[1]-state.getPos()[1]
                        sortedClusters[s]['V'].append( [clkey,L,B[0],state.getPos()[1],mat,(A[2]+B[2])/2.] )
                        rc = h['res'+str(s)+'V'].Fill( (A[0]+B[0])/2.-state.getPos()[0])
              else:  
                        # Horizontal 
                        L = A[0]-state.getPos()[0]
                        sortedClusters[s]['H'].append( [clkey,L,A[1],state.getPos()[0],mat,(A[2]+B[2])/2.] )
                        rc = h['res'+str(s)+'H'].Fill( (A[1]+B[1])/2.-state.getPos()[1])

          # Loop over station 
          for s in range(1,6):

              # Find station with exactly 1x and 1y clusters:
              if not (len(sortedClusters[s]['V']) * len(sortedClusters[s]['H']) ) ==1: continue

              # Corrected time between 2 axes  
              # FIRST PLANE time correction
              timeCorr = {}
              for proj in ['V','H']:
                  clkey = sortedClusters[s][proj][0][0] # HitID of the fastest cluster [First plane - front track]
                  aCl   = event.Cluster_Scifi[clkey] # Get cluster time - fastest hit
                  L = sortedClusters[s][proj][0][1] # Get L - distance of a real hit - taking into account the propagation  
                  rc = h['extrap'+str(s)+proj].Fill(abs(L)) # extrapolation 
                  time = aCl.GetTime()   # Get time in ns, use fastest TDC of cluster
                  mat = sortedClusters[s][proj][0][4] # Mat number 
                  time-=  self.tdcScifiStationCalib[s][1][proj][mat] # alignment correct as function of station / projection / mat
                  time-=  self.tdcScifiStationCalib[s][0] # Internal calibration 

                  # Get time for each orientation  
                  timeCorr[proj] = time - abs(L)/self.V 


              # Difference between orientations 
              dt = timeCorr['H']  - timeCorr['V']

              # Sonething I don't know 
              rc = h['CTR_Scifi'+str(s)+tag].Fill(dt)

              # Get first MAT NUMBER 
              matH,matV = sortedClusters[s]['H'][0][4],sortedClusters[s]['V'][0][4]
              rc = h['CTR_Scifi'+str(100*s+10*matH+matV)+tag].Fill(dt)

              # 
              if abs(slopeX)<0.1 and abs(slopeY)<0.1:  
                    rc = h['CTR_Scifi_beam'+str(s)+tag].Fill(dt)
                    rc = h['CTR_Scifi_beam'+str(100*s+10*matH+matV)+tag].Fill(dt)
              dR = sortedClusters[s]['V'][0][2] - sortedClusters[s]['H'][0][3]
              rc = h['resX'+str(s)+'V'].Fill(dR)
              dR = sortedClusters[s]['H'][0][2]-sortedClusters[s]['V'][0][3]
              rc = h['resX'+str(s)+'H'].Fill(dR)
#
              if tag!='v0':
                 stationTimes = {}
                 for s in range(1,6):
                   if not (len(sortedClusters[s]['V']) * len(sortedClusters[s]['H']) ) ==1: continue
                   sTime = 0
                   for proj in ['V','H']:
                      clkey = sortedClusters[s][proj][0][0]
                      aCl    = event.Cluster_Scifi[clkey]
                      L = sortedClusters[s][proj][0][1]
                      time =  aCl.GetTime()   # Get time in ns, use fastest TDC of cluster
                      mat  =  sortedClusters[s][proj][0][4]
                      time-=  self.tdcScifiStationCalib[s][1][proj][mat]
                      time-=  self.tdcScifiStationCalib[s][0]
                      time-=  abs(L)/self.V
                      sTime += time
                   stationTimes[s] = [sTime/2.,(sortedClusters[s]['H'][0][5] + sortedClusters[s]['V'][0][5])/2.]
                 for s1 in range(1,5):
                     if not s1 in stationTimes: continue
                     for s2 in range(s1+1,6):
                         if not s2 in stationTimes: continue
                         dT = stationTimes[s2][0] - stationTimes[s1][0]
# correct for slope
                         dZ = stationTimes[s2][1] - stationTimes[s1][1]
                         dL = dZ * ROOT.TMath.Sqrt( slopeX**2+slopeY**2+1 )
                         if slopeY>0.1:  dL = -dL     # cosmics from the back
                         dT -= dL / self.C
                         rc = h['CTR_ScifiStation'+str(s1*10+s2)+tag].Fill(dT)
                         if abs(slopeX)<0.1 and abs(slopeY)<0.1:
                               rc = h['CTR_ScifiStation_beam'+str(s1*10+s2)+tag].Fill(dT)

   def Plot(self):
      h = self.M.h
      tag =  self.tag
      for b in ['','_beam']:
         ut.bookCanvas(h,'CTR'+b+tag,'CTR'+tag,1800,1200,3,2)
         for s in range(1,6): 
             tc =  h['CTR'+b+tag].cd(s)
             histo = h['CTR_Scifi'+b+str(s)+tag]
             rc = histo.Fit('gaus','SQ')
             tc.Update()
             stats = histo.FindObject('stats')
             stats.SetOptFit(1111111)
             stats.SetX1NDC(0.62)
             stats.SetY1NDC(0.63)
             stats.SetX2NDC(0.98)
             stats.SetY2NDC(0.94)
             histo.Draw()

         for s in range(1,6):
             ut.bookCanvas(h,'CTRM'+str(s)+b+tag,'CTR per mat combi',1800,1200,3,3)
             j = 1
             for matH in range(3):
                for matV in range(3):
                     tc =  h['CTRM'+str(s)+b+tag].cd(j)
                     j+=1
                     histo = h['CTR_Scifi'+b+str(100*s+10*matH+matV)+tag]
                     histo.Fit('gaus','SQ')
                     tc.Update()
                     stats = histo.FindObject('stats')
                     stats.SetOptFit(1111111)
                     stats.SetX1NDC(0.62)
                     stats.SetY1NDC(0.63)
                     stats.SetX2NDC(0.98)
                     stats.SetY2NDC(0.94)
                     histo.Draw()

      if tag!='v0':
        for b in ['','_beam']:
           ut.bookCanvas(h,'CTRS'+b,'CTR per station combination'+tag,1800,1200,5,2)
           k=1
           for s1 in range(1,5):
              for s2 in range(s1+1,6):
                  tc = h['CTRS'+b].cd(k)
                  k+=1
                  histo = h['CTR_ScifiStation'+b+str(s1*10+s2)+tag]
                  histo.Draw()
                  histo.Fit('gaus','SQ')
                  tc.Update()
                  stats = histo.FindObject('stats')
                  stats.SetOptFit(1111111)
                  stats.SetX1NDC(0.62)
                  stats.SetY1NDC(0.63)
                  stats.SetX2NDC(0.98)
                  stats.SetY2NDC(0.94)
                  histo.Draw()

   def ExtractMeanAndSigma(self):
      self.meanAndSigma = {}
      h = self.M.h
      tag =  self.tag
      ut.bookHist(h,'cor')
      for b in ['','_beam']:
         self.meanAndSigma[b]={}
         for s in range(1,6): 
             for matH in range(3):
                for matV in range(3):
                     key = 100*s+10*matH+matV
                     histo = h['CTR_Scifi'+b+str(key)+tag]
                     Fun = histo.GetFunction('gaus')
                     self.meanAndSigma[b][key] = [Fun.GetParameter(1),Fun.GetParameter(2)]

   def minimize(self,b=""):
      h = self.M.h
      self.ExtractMeanAndSigma()
      ut.bookHist(h,'commonBlock','',100,0.,100.)

      for s in range(1,6):
         for matH in range(3):
            for matV in range(3):
               key = 100*s+10*matH+matV
               dt = self.meanAndSigma[b][key][0]
               h['commonBlock'].SetBinContent(matH*10+matV,dt)
         npar = 2*3
         ierflg    = ctypes.c_int(0)
         vstart  = array('d',[0]*npar)
         gMinuit = ROOT.TMinuit(npar)
         gMinuit.SetFCN(FCN)
         gMinuit.SetErrorDef(1.0)
         gMinuit.SetMaxIterations(10000)
         err = 1E-3
         p = 0
         for proj in ['H','V']:
           for m in range(3):
             name = "s"+str(s)+proj+str(m)
             gMinuit.mnparm(p, name, vstart[p], err, 0.,0.,ierflg)
             p+=1
         gMinuit.FixParameter(0)
         strat = array('d',[0])
         gMinuit.mnexcm("SET STR",strat,1,ierflg) # 0 faster, 2 more reliable
         gMinuit.mnexcm("SIMPLEX",vstart,npar,ierflg)
         gMinuit.mnexcm("MIGRAD",vstart,npar,ierflg)

         cor    = ctypes.c_double(0)
         ecor  = ctypes.c_double(0)
         p = 0
         for proj in ['H','V']:
           for m in range(3):
             rc = gMinuit.GetParameter(p,cor,ecor)
             p+=1
             self.tdcScifiStationCalib[s][1][proj][m] = cor.value

      with open('ScifiTimeAlignment_v1', 'wb') as fh:
           pickle.dump(self.tdcScifiStationCalib, fh)

   def minimizeStation(self,b=""):
      h = self.M.h
      tag = self.tag
      self.meanAndSigmaStation = {}
      self.meanAndSigmaStation[b]={}
      for s1 in range(1,6): 
           for s2 in range(s1+1,6): 
                 key = s1*10+s2
                 histo = h[ 'CTR_ScifiStation'+b+str(key)+tag]
                 Fun = histo.GetFunction('gaus')
                 self.meanAndSigmaStation[b][key] = [Fun.GetParameter(1),Fun.GetParameter(2)]
      for s1 in range(1,6):
         for s2 in range(s1+1,6): 
            key = 10*s1+s2
            dt = self.meanAndSigmaStation[b][key][0]
            h['commonBlock'].SetBinContent(key,dt)
         npar = 5
         ierflg    = ctypes.c_int(0)
         vstart  = array('d',[0,-0.3365,-0.975,0.11,0.239])
         gMinuit = ROOT.TMinuit(npar)
         gMinuit.SetFCN(FCNS)
         gMinuit.SetErrorDef(1.0)
         gMinuit.SetMaxIterations(10000)
         err = 1E-3
         p = 0
         for s in range(1,6):
             name = "station"+str(s)
             gMinuit.mnparm(p, name, vstart[p], err, 0.,0.,ierflg)
             p+=1
         gMinuit.FixParameter(0)
         strat = array('d',[0])
         gMinuit.mnexcm("SET STR",strat,1,ierflg) # 0 faster, 2 more reliable
         gMinuit.mnexcm("SIMPLEX",vstart,npar,ierflg)
         gMinuit.mnexcm("MIGRAD",vstart,npar,ierflg)

         cor    = ctypes.c_double(0)
         ecor  = ctypes.c_double(0)
         for s in range(1,6):
             rc = gMinuit.GetParameter(s-1,cor,ecor)
             self.tdcScifiStationCalib[s][0] = cor.value

      with open('ScifiTimeAlignment_v2', 'wb') as fh:
           pickle.dump(self.tdcScifiStationCalib, fh)

class Scifi_TimeOfTracks(ROOT.FairTask):
   " dt versus dz"
   def Init(self,monitor):
       self.M = monitor
       h = self.M.h
       self.V = 15 * u.cm/u.ns
       self.C = 299792458 * u.m/u.s
       ut.bookHist(M.h,'dTvsZ','dT versus dL; dL/0.5cm [cm];dT/100ps [ns]',140,0.,70.,120,-6.,6.)
       ut.bookHist(M.h,'dTvsZ_beam','dT versus dL, beam dL/0.5cm [cm];dT/100ps [ns]',140,0.,70.,120,-6.,6.)
       with open('ScifiTimeAlignment_v2', 'rb') as fh:
           self.tdcScifiStationCalib = pickle.load(fh)

   def ExecuteEvent(self,event):
       h = self.M.h
       for aTrack in event.Reco_MuonTracks:
          if not aTrack.GetUniqueID()==1: continue
          fitStatus = aTrack.getFitStatus()
          if not fitStatus.isFitConverged(): continue
          state = aTrack.getFittedState()
          mom = state.getMom()
          slopeX = mom.X()/mom.Z()
          slopeY = mom.Y()/mom.Z()
          sortedClusters={}
          DetID2Key={}
          for nHit in range(event.Digi_ScifiHits.GetEntries()):
            DetID2Key[event.Digi_ScifiHits[nHit].GetDetectorID()] = nHit
#
          pos = {}
          for s in range(1,6):  sortedClusters[s] = {'H':[],'V':[]}
          for nM in range(aTrack.getNumPointsWithMeasurement()):
              state = aTrack.getFittedState(nM)
              Meas = aTrack.getPointWithMeasurement(nM)
              W      = Meas.getRawMeasurement()
              clkey = W.getHitId()
              aCl    = event.Cluster_Scifi[clkey]
              aHit = event.Digi_ScifiHits[DetID2Key[aCl.GetFirst()]]
              s = aCl.GetFirst()//1000000
              aCl.GetPosition(A,B)
              mat = (aCl.GetFirst()//10000)%10

              if aHit.isVertical(): 
                        L = B[1]-state.getPos()[1]
                        sortedClusters[s]['V'].append( [clkey,L,B[0],state.getPos()[1],mat,(A[2]+B[2])/2.] )
              else:  
                        L = A[0]-state.getPos()[0]
                        sortedClusters[s]['H'].append( [clkey,L,A[1],state.getPos()[0],mat,(A[2]+B[2])/2.] )
          stationTimes = {}
          for s in range(1,6):
             if not (len(sortedClusters[s]['V']) * len(sortedClusters[s]['H']) ) ==1: continue
             sTime = 0
             for proj in ['V','H']:
                clkey = sortedClusters[s][proj][0][0]
                aCl    = event.Cluster_Scifi[clkey]
                L = sortedClusters[s][proj][0][1]
                time =  aCl.GetTime()   # Get time in ns, use fastest TDC of cluster
                mat  =  sortedClusters[s][proj][0][4]
                time-=  self.tdcScifiStationCalib[s][1][proj][mat]  # correct as function of station / projection / mat
                time-=  self.tdcScifiStationCalib[s][0]                  # internal station calibration
                time-=  abs(L)/self.V

# cross check 
               # corTime = self.M.Scifi.GetCorrectedTime(aCl.GetFirst(),aCl.GetTime(),abs(L) )
               # print('test',aCl.GetTime(),time,corTime)

                sTime += time
             stationTimes[s] = [sTime/2.,(sortedClusters[s]['H'][0][5] + sortedClusters[s]['V'][0][5])/2.]
          # require station 1 to be present which defines T0
          if not 1 in stationTimes: continue

          T0 = stationTimes[1][0]
          Z0 = stationTimes[1][1]
          for s in stationTimes:
             if s == 1: continue
             dZ = stationTimes[s][1]-Z0
             dT = stationTimes[s][0]-T0
             dL = dZ * ROOT.TMath.Sqrt( slopeX**2+slopeY**2+1 )
             # if slopeY>0.1:  dL = -dL     # cosmics from the back
             # dT -= dL / self.C
             rc = h['dTvsZ'].Fill(dL,dT)
             if abs(slopeX)<0.1 and abs(slopeY)<0.1:
                  rc = h['dTvsZ_beam'].Fill(dL,dT)



   def Plot(self):
      h = self.M.h
      ut.bookCanvas(h,'Tscifi','',1800,1200,2,1)
      h['Tscifi'].cd(1)
      h['dTvsZ'].Draw('colz')
      h['Tscifi'].cd(2)
      h['dTvsZ_beam'].Draw('colz')

class histStore():
     h = {}
     xCheck = ''

if __name__ == '__main__':
   import Monitor
   from argparse import ArgumentParser
   parser = ArgumentParser()
   parser.add_argument("-f", "--inputFile", dest="fname", help="file name", type=str,default='RunWithTracks4208.root',required=False)
   parser.add_argument("-g", "--geoFile", dest="geoFile", help="file name", type=str,default=None,required=False)
   parser.add_argument("-c", "--command", dest="command", help="command",required=False,default="")
   parser.add_argument("-r", "--runNumber", dest="runNumber", help="run number", type=int,default=0)
   parser.add_argument("-p", "--path", dest="path", help="path to file",required=False,default="")
   parser.add_argument("-P", "--partition", dest="partition", help="partition of data", type=int,required=False,default=-1)
   parser.add_argument("-M", "--online", dest="online", help="online mode",default=False,action='store_true')
   options = parser.parse_args()

   if options.geoFile:
        M = Monitor.Monitoring(options,{})
   else:
        M = histStore()

   F =  ROOT.TFile(options.fname)
   eventTree = F.rawConv

   if options.command == "full":
       task = Scifi_CTR()
       M.iteration = 'v0'
       task.Init(M)
       for event in eventTree:
            task.ExecuteEvent(event)
            event.Reco_MuonTracks.Delete()
       task.Plot()
       task.minimize(b="")   # all tracks, not yet enough stats for beam tracks
# cross check and station alignment
       M.iteration = 'v1'
       task.Init(M)
       for event in eventTree:
            task.ExecuteEvent(event)
            event.Reco_MuonTracks.Delete()
       task.Plot()
# nw minimize the station alignments
       task.minimizeStation(b="")

# cross check
       M.iteration = 'v2'
       task.Init(M)
       for event in eventTree:
            task.ExecuteEvent(event)
            event.Reco_MuonTracks.Delete()
       task.Plot()
       ut.writeHists(M.h,'ScifiTimeCalibration.root',plusCanvas=True)

       for s in range(1,6):
          C = taskT.tdcScifiStationCalib[s]
          print ("station %1i  %5.2F  H: %5.2F  %5.2F  %5.2F   V:  %5.2F  %5.2F  %5.2F "%( s, C[0],C[1]['H'][0], C[1]['H'][1], C[1]['H'][2],C[1]['V'][0], C[1]['V'][1], C[1]['V'][2] ) )
       for s in range(1,6):
          C = taskT.tdcScifiStationCalib[s]
          print ("station %1i  %5.3F*u.ns,  %5.3F*u.ns,  %5.3F*u.ns,  %5.3F*u.ns,   %5.3F*u.ns,  %5.3F*u.ns,  %5.3F*u.ns "%( s, C[0],C[1]['H'][0], C[1]['H'][1], C[1]['H'][2],C[1]['V'][0], C[1]['V'][1], C[1]['V'][2] ) )

if options.command == "full" or options.command == "check":
# final test
       taskT = Scifi_TimeOfTracks()
       taskT.Init(M)
       for event in eventTree:
            taskT.ExecuteEvent(event)
            event.Reco_MuonTracks.Delete()
       taskT.Plot()
