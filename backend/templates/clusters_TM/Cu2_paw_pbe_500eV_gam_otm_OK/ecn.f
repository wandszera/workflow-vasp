      parameter(ns=500)
      parameter(nl=100000)
  
      integer  i,j,k,nscell,sym(nl)
      integer  i1,j1,k1,i2,nlcell,kk
      REAL*8  rsx(ns),rsy(ns),rsz(ns)
      REAL*8  rsxc(ns),rsyc(ns),rszc(ns)
      REAL*8  rlx(nl),rly(nl),rlz(nl)
      REAL*8  rlxc(nl),rlyc(nl),rlzc(nl) 
      REAL*8  r(ns,nl)
      REAL*8  rmin(ns),rwabl(ns),ecnatomi(ns)
      REAL*8  sum0,sum1,sum2
      REAL*8  r0,r1,delta
      REAL*8  a11, a12, a13, a21, a22, a23, a31, a32, a33
c
      open(2,file='POSCAR',status='old')
      open(3,file='ecn_history.dat',status='unknown')
      open(6,file='ecn_bonds.dat.',status='unknown')
      open(7,file='ecn_results.dat',status='unknown')
      open(8,file='ecn_forplot.dat',status='unknown')
c
      read(2,*)
      read(2,*)
      read(2,*) a11, a21, a31 
      read(2,*) a12, a22, a32
      read(2,*) a13, a23, a33
      read(2,*)
      read(2,*) nscell 
      read(2,*)
c      write(*,*) 'provide total number of atoms in the cell'
c      read(*,*) nscell
c
c     Variables set up
c
      do i=1,ns,1 
         rsx(i) = 0.0d0
         rsy(i) = 0.0d0
         rsz(i) = 0.0d0
         rsxc(i) = 0.0d0
         rsyc(i) = 0.0d0
         rszc(i) = 0.0d0         
      enddo
c    
      do i=1,nl,1 
         rlx(i) = 0.0d0
         rly(i) = 0.0d0
         rlz(i) = 0.0d0
         rlxc(i) = 0.0d0
         rlyc(i) = 0.0d0
         rlzc(i) = 0.0d0
      enddo 
c
c     Read POSCAR file and re-write the atomic positions in ECN_history
c
      write(3,*) nscell
      do i=1,nscell,1
         read(2,*) rsx(i), rsy(i), rsz(i)
         write(3,200) rsx(i),rsy(i),rsz(i) 
 200     format(3F20.16)
      enddo
c
c    Generate multiple unit cells 
c     
      i2=1 
      do i1=-2,2,1
         do j1=-2,2,1
            do k1=-2,2,1
               do i=1,nscell,1
                  rlx(i2) = rsx(i) + i1 
                  rly(i2) = rsy(i) + j1
                  rlz(i2) = rsz(i) + k1
                  sym(i2) = i
                  write(3,*) i2, sym(i2), rlx(i2), rly(i2), rlz(i2)
                  i2=i2+1
               enddo
            enddo
         enddo
      enddo
c
c     determine the number of atoms in the large cell
c
      nlcell = i2-1
      write(3,*) nlcell
c
c     convert to cartesian coordinates 
c
      do i=1,nscell,1
       rsxc(i) = rsx(i)*a11 + rsy(i)*a12 + rsz(i)*a13
       rsyc(i) = rsx(i)*a21 + rsy(i)*a22 + rsz(i)*a23
       rszc(i) = rsx(i)*a31 + rsy(i)*a32 + rsz(i)*a33
       write(3,*) rsxc(i), rsyc(i), rszc(i) 
      enddo  
      do i=1,nlcell
       rlxc(i) = rlx(i)*a11 + rly(i)*a12 + rlz(i)*a13
       rlyc(i) = rlx(i)*a21 + rly(i)*a22 + rlz(i)*a23
       rlzc(i) = rlx(i)*a31 + rly(i)*a32 + rlz(i)*a33     
       write(3,*) rlxc(i), rlyc(i), rlzc(i) 
      enddo    
c
c     set up variables: distances
c 
      do i=1,ns
         do j=1,nl
            r(i,j) = 0.0d0
         enddo
      enddo
c
c     Calculate the bond length between the ns-atoms in nscell with 
c     the nl-atoms in the nlcell 
c
      do i=1,nscell
       do j=1,nlcell
         r(i,j) = sqrt( (rsxc(i) - rlxc(j))**2 + 
     &                  (rsyc(i) - rlyc(j))**2 + 
     &                  (rszc(i) - rlzc(j))**2 )
         write(3,*) i, sym(j), r(i,j) 
       enddo
      enddo
c
c     [1] Determine the smallest bond length for each atom
c 
      do i=1,nscell
         rmin(i) = 100.0d0
      enddo
c
c
c
      do i=1,nscell
        jj = 0
        do j=1,nlcell
           if (r(i,j) <= rmin(i) .and. r(i,j) >= 1.0d0) then
              rmin(i) = r(i,j)
              jj = j
           endif
        enddo
        write(3,101) i, sym(jj), rmin(i)
        write(7,101) i, sym(jj), rmin(i)
 101    format(2I4,F8.4)
      enddo 
c
c    [2] Weighted average bond length
c    rwabl = [ sum_i bond_i*exp(1 - (bond_i/rmin(i))**6]/
c            [sum_i exp(1 - (bond_i/rmin(i))**6]
c
 405  continue
      write(7,511)
 511  format('Atom weighted average bond length (Awabl)')
      do i=1,nscell
         rwabl(i) = 0.0d0
      enddo
c
      sum0 = 0.0d0
      sum1 = 0.0d0
      sum2 = 0.0d0
      do i=1,nscell
         do j=1,nlcell
            sum0 = exp(1 - (r(i,j)/rmin(i))**6)
            if (sum0.le.1.0d-3) sum0 = 0.0d0
            sum1 = sum1 + r(i,j)*sum0
            sum2 = sum2 + sum0
         enddo
c
c        There is no double counting in sum1 because r(k,k)*sum0, r(k,k)=0.0
c        Remove double counting in sum2, e.g., r(k,k)
c
         sum2 = sum2 - exp(1.0)
         rwabl(i) = sum1/sum2
         write(7,788) i,rmin(i),rwabl(i),abs(rwabl(i)-rmin(i))
         sum0 = 0.0d0
         sum1 = 0.0d0
         sum2 = 0.0d0
 788     format(I3,3F8.4)
       enddo

c
c      Calculate total weighted bond length
c
       sum0 = 0.0d0
       sum1 = 0.0d0
       sum2 = 0.0d0
       do i=1,nscell
          sum0 = sum0 + rwabl(i)
       enddo
       sum1 = sum0/nscell
       write(7,789) sum1
 789   format('Total weigthed average bond length =',F8.4)
       write(7,*)
c
c     apply a self-consistent process in obtaining the
c     weigthed average bond length for each atom.
c     If rwabl(i) - rmin(i) >= 0.0001d0, then it uses the
c     values of rwabl(i) as rmin(i) e a new set of rwabl(i)
c     are calculated. If it is smaller, rwabl(i) keeps is
c     value and the bond weight are calculated and the
c     ECN is obtained. This procedure is required for the
c     clusters to the wide broad of the bond lengths.
c     It affects very small the ECN.
       do i=1,nscell
          if (abs(rwabl(i) - rmin(i)) >= 0.0001d0) then
             do j=1,nscell
                rmin(j) = rwabl(j)
             enddo
             goto 405
           endif
        enddo
c
c      Calculate the bond weight
c
       write(7,*)
       do i=1,nscell
          ecnatomi(i) = 0.0d0
       enddo
c
       sum0 = 0.0d0
       sum1 = 0.0d0
       sum2 = 0.0d0
       do i=1,nscell
          write(7,792) i
c         wabl = Weighted average bond length
c         bl   = bond length
c         wecn = weigh effective coordination number
 792      format('Atom ',I3,' wabl    bl      wecn')
          do j=1,nlcell
             sum0 = exp(1 - (r(i,j)/rwabl(i))**6)
             if(sum0.le.1.0d-3) sum0=0.0d0
             sum1 = sum1 + sum0
             if (sum0 >= 0.01d0 .and. sum0 <= 2.70d0) then
       write(7,791) i,sym(j),rwabl(i),r(i,j),sum0,abs(r(i,j)-rwabl(i))
 791            format(2I4,4F8.4)
             endif
          enddo

c         remove double counting

          sum1 = sum1 - exp(1.0)
          ecnatomi(i) = sum1

          sum0 = 0.0d0
          sum1 = 0.0d0
          sum2 = 0.0d0
          write(7,790) ecnatomi(i)
 790      format('ECN =',F8.4)
          write(7,*)
        enddo
c
c       write all ECN_i numbers
c
        do i=1,nscell,1
           write(7,900) i, ecnatomi(i)
 900       format(i4,F8.4)
        enddo
        write(7,*) 
c
c       Average effective coordination number for the cluster
c       Sum of all effective coordination number divided by the
c       number of atoms
c
        sum0 = 0.0d0
        sum1 = 0.0d0
        do i=1,nscell
         sum0 = sum0 + ecnatomi(i)
        enddo
        sum1 = sum0/nscell
        write(7,795) sum0, nscell, sum1
 795    format(F8.4,I4,2x,'Total average ECN =',F8.4)

c
c     bond distribution in each 0.050\AA space
c     All bond lengths are allocated in the r(i,j) array.
c     Below, we will count the number of bond lengths in the
c     range, r0 < bond_length < r1. A file is written, which
c     should be used for plot all clusters. This is done to
c     obtain a correct value for rcut. We would like to obtain
c     the average bond length of the first peak in the bond
c     length distribution.
c
      r0 = 0.0d0
      r1 = 0.0d0
      delta = 0.050d0
      r1 = r0+delta
 100  continue
      kk = 0
      do i=1,nscell
       do j=1,nlcell
        if(r(i,j).GT.r0.and.r(i,j).LE.r1) kk = kk + 1
       enddo
      enddo
      write(6,400) r0, kk
 400  format(F10.6,I5)
      if(r1.GT.10.0d0) then
        goto 150 
       else
        r0 = r1
        r1 = r1+delta
        goto 100
      endif
c
c     Effective coordination number distribution
c
 150  continue
      r0 = 0.0d0
      r1 = 0.0d0
      delta = 0.10d0
      r1 = r0+delta
 250  continue
      kk = 0
      do i=1,nscell,1
        if(ecnatomi(i).GT.r0.and.ecnatomi(i).LE.r1) kk = kk+1
      enddo
      write(8,420) r0, kk
 420  format(F10.6,I5)
      if(r1.GT.40.0d0) then
        stop
       else
        r0 = r1
        r1 = r1+delta
        goto 250
      endif
      stop
      end
