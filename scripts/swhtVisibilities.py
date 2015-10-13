#!/usr/bin/env python
"""
Perform a Spherical Wave Harmonic Transform on LOFAR ACC/XST data or widefield MS data (e.g. PAPER) to form a complex or Stokes dirty image dirty image
"""

#TODO: test PAPER
#TODO: how to handle polarization
#TODO: how does weighting work?
#TODO: Multiple frequencies
#TODO: Multiple LOFAR files, build sphere with different limits for each file
#TODO: apply LOFAR gain solutions
#TODO: replace ephem with astropy.coordinates
#TODO: clean-up options
#TODO: option: image from coefficients

import numpy as np
from matplotlib import pyplot as plt
import datetime
import ephem
import pyrap.tables as pt
import sys,os
import SWHT

#import scipy.constants
#cc = scipy.constants.c
cc = 299792458.0 #speed of light, m/s

if __name__ == '__main__':
    from optparse import OptionParser
    o = OptionParser()
    o.set_usage('%prog [options] ACC/XST/MS FILE')
    o.set_description(__doc__)
    o.add_option('--station', dest='station', default=None,
        help = 'LOFAR ONLY: station name, e.g. SE607, if this is used then the ant_field and ant_array options are not required, default: None')
    o.add_option('-F', '--ant_field', dest='ant_field', default=None,
        help = 'LOFAR ONLY: AntennaField.conf file for the LOFAR station of the ACC files, default: None')
    o.add_option('-A', '--ant_array', dest='ant_array', default=None,
        help = 'LOFAR ONLY: AntennaArray.conf file for the LOFAR station geographical coordinates, default: None')
    o.add_option('-D', '--deltas', dest='deltas', default=None,
        help = 'LOFAR ONLY: iHBADeltas.conf file, only required for HBA imaging, default: None')
    o.add_option('-r', '--rcumode', dest='rcumode', default=3, type='int',
        help = 'LOFAR ONLY: Station RCU Mode, usually 3,5,6,7, for XST it will override filename metadata default: 3(LBA High)')
    o.add_option('-s', '--subband', dest='subband', default=0, type='int',
        help = 'Select which subband(s) to image, for ACC and MS it will select, for XST it will override filename metadata, default:0')
    #o.add_option('-p', '--pixels', dest='pixels', default=64, type='int',
    #    help = 'Width of image in pixels, default: 64')
    o.add_option('-C', '--cal', dest='calfile', default=None,
        help = 'LOFAR ONLY: Apply a calibration soultion file to the data.')
    #o.add_option('-S', '--save', dest='savefig', default=None,
    #    help = 'Save the figure using this name, type is determined by extension')
    #o.add_option('--conv', dest='conv', default='fast',
    #    help = 'If using FFT, choose a convolution function: fast(nearest neighbor), rectangle, gaussian, prolate spheroid. default:fast')
    #o.add_option('--dft', dest='dft', action='store_true',
    #    help = 'Form image with a direct FT instead of an FFT')
    o.add_option('--nodisplay', dest='nodisplay', action='store_true',
        help = 'Do not display the generated image')
    #o.add_option('--pkl', dest='pkl', default=None,
    #    help = 'Save complex images in a numpy array in a pickle file using this name (include .pkl extention), default: tempImage.pkl')
    o.add_option('-i', '--int', dest='int_time', default=1., type='float',
        help = 'LOFAR ONLY: Integration time, used for accurate zenith pointing, for XST it will override filename metadata, default: 1 second')
    o.add_option('-c', '--column', dest='column', default='CORRECTED_DATA', type='str',
        help = 'MS ONLY: select which data column to image, default: CORRECTED_DATA')
    o.add_option('--override', dest='override', action='store_true',
        help = 'LOFAR XST ONLY: override filename metadata for RCU, integration length, and subband')
    o.add_option('--autos', dest='autos', action='store_true',
        help = 'Include the auto-correlation in the image, by default they are blanked')
    #o.add_option('--weight', dest='weighting', default='natural',
    #    help = 'Weighting mode, natural (default), uniform')
    #o.add_option('--fov', dest='fov', default=180., type='float',
    #    help = 'Field of View in degrees, default: 180 (all-sky)')
    o.add_option('-l', '--lmax', dest='lmax', default=32, type='int',
        help = 'Maximum l spherical harmonic quantal number, rule-of-thumb: used number of antenna elements, default: 32')
    o.add_option('--ocoeffs', dest='ocoeffs', default=None,
        help = 'Save output image coefficients to a pickle file using this name (include .pkl extention), default: tempCoeffs.pkl')
    #o.add_option('--icoeffs', dest='icoeffs', default=None,
    #    help = 'Load an image coefficients pickle file and generate an image')
    opts, args = o.parse_args(sys.argv[1:])

    visFile = args[0]
    fDict = SWHT.fileio.parse(visFile)

    #Pull out the visibility data in a (u,v,w) format
    if fDict['fmt']=='acc' or fDict['fmt']=='xst': #LOFAR visibilities
        if fDict['fmt']=='acc' or opts.override:
            fDict['rcu'] = opts.rcumode #add the RCU mode to the meta data of an ACC file, or override the XST metadat
            fDict['sb'] = int(opts.subband)
            fDict['int'] = opts.int_time

        lofarStation = SWHT.lofarConfig.getLofarStation(name=opts.station, affn=opts.ant_field, aafn=opts.ant_array, deltas=opts.deltas) #get station position information

        #longitude and latitude of array
        #TODO: this is the only point in which antArrays is used, replace with converting the station ITRF X,Y,Z< position to geodetic, currently using ecef.py but the results are only approximately correct
        #lon, lat, elev = lofarStation.antArrays.location[SWHT.lofarConfig.rcuInfo[fDict['rcu']]['array_type']]
        arr_xyz = lofarStation.antField.location[SWHT.lofarConfig.rcuInfo[fDict['rcu']]['array_type']]
        lat, lon, elev = SWHT.ecef.ecef2geodetic(arr_xyz[0], arr_xyz[1], arr_xyz[2], degrees=True)
        print 'LON(deg):', lon, 'LAT(deg):', lat, 'ELEV(m):', elev

        #antenna positions
        ants = lofarStation.antField.antpos[SWHT.lofarConfig.rcuInfo[fDict['rcu']]['array_type']]
        if 'elem' in fDict: #update the antenna positions if there is an element string
            if lofarStation.deltas is None:
                print 'Warning: HBA element string found, but HBADeltas file is missing, your image is probably not going to make sense'
            else:
                print 'Updating antenna positions with HBA element deltas'
                for aid in np.arange(ants.shape[0]):
                    delta = lofarStation.deltas[int(fDict['elem'][aid], 16)]
                    delta = np.array([delta, delta])
                    ants[aid] += delta
        nants = ants.shape[0]
        print 'NANTENNAS:', nants

        #frequency information
        nchan = SWHT.lofarConfig.rcuInfo[fDict['rcu']]['nchan']
        bw = SWHT.lofarConfig.rcuInfo[fDict['rcu']]['bw']
        df = bw/nchan
        freq = fDict['sb']*df + SWHT.lofarConfig.rcuInfo[fDict['rcu']]['offset']
        print 'SUBBAND: %i (%f MHz)'%(fDict['sb'], freq/1e6)

        #get correlation matrix for a single subband
        npols = 2
        nantpol = nants * npols
        print 'Reading in visibility data file ...',
        if fDict['fmt']=='acc':
            corrMatrix = np.fromfile(visFile, dtype='complex').reshape(nchan, nantpol, nantpol) #read in the complete correlation matrix
            corrMatrix = corrMatrix[fDict['sb'], :, :] #select out a single subband, shape (nantpol, nantpol)

            #correct the time due to subband stepping
            tOffset = (nchan - fDict['sb']) * fDict['int'] #the time stamp in the filename in for the last subband
            rem = tOffset - int(tOffset) #subsecond remainder
            fDict['ts'] = fDict['ts'] - datetime.timedelta(0, int(tOffset), rem*1e6)
        elif fDict['fmt']=='xst':
            corrMatrix = np.fromfile(visFile, dtype='complex').reshape(nantpol, nantpol) #read in the correlation matrix
        print 'done'
        print 'CORRELATION MATRIX SHAPE', corrMatrix.shape
        
        ##TODO: get working correctly
        ##read cal file if included and apply agin solutions
        #if not (opts.calfile is None):
        #    antGains = np.fromfile(opts.calfile, dtype='complex').reshape(nchan, nants, npols)
        #    xAntGains = antGains[:,:,0]
        #    yAntGains = antGains[:,:,1]
        #    for sid,sb in enumerate(sbs):
        #        calxSB=calx[sb]
        #        calxSB=np.reshape(calxSB,(96,1))
        #        gains=np.conj(calxSB) * np.transpose(calxSB)
        #        polAcc=np.multiply(polAcc,gains) 
        
        obs = ephem.Observer() #create an observer at the array location
        obs.long = lon * (np.pi/180.)
        obs.lat = lat * (np.pi/180.)
        #TODO: I don't trust the elev value returned from ecef.ecef2geodetic()
        #obs.elevation = float(elev)
        obs.elevation = 0.
        obs.epoch = fDict['ts']
        obs.date = fDict['ts']
        print 'Observatory:', obs

        #src = ephem.FixedBody() #create a source at zenith
        #src._ra = obs.sidereal_time()
        #src._dec = obs.lat
        #src.compute(obs)
        #
        ##get antenna positions in ITRF (x,y,z) format and compute the (u,v,w) coordinates pointing at zenith
        #xyz = []
        #for a in ants: xyz.append([a[0,0]+arr_xyz[0], a[0,1]+arr_xyz[1], a[0,2]+arr_xyz[2]])
        #xyz = np.array(xyz)
        ##uvw = SWHT.ft.xyz2uvw(xyz, src, obs, np.array([freq])).reshape(nants*nants,3)
        #uvw = SWHT.ft.xyz2uvw(xyz, src, obs, np.array([cc])).reshape(nants*nants,3) #HACK: convert xyz to uvw but keep in units of meters
        #print np.reshape(uvw[:,0], (96, 96))

        ##uv coverage plot
        #plt.plot(uvw[:,0], uvw[:,1], '.')
        #plt.show()

        #in order to accommodate multiple observations at different times/sidereal times all the positions need to be rotated relative to sidereal time 0
        LSTangle = obs.sidereal_time() #radians
        rotMatrix = np.array([[np.cos(LSTangle), -1.*np.sin(LSTangle), 0.],
                              [np.sin(LSTangle), np.cos(LSTangle),     0.],
                              [0.,               0.,                   1.]]) #rotate about the z-axis
        #get antenna positions in ITRF (x,y,z) format and compute the (u,v,w) coordinates referenced to sidereal time 0, this works only for zenith snapshot xyz->uvw conversion
        xyz = []
        for a in ants:
            xyz.append(np.dot(a[0], rotMatrix))
        xyz = np.array(xyz)
        repxyz = np.repeat(xyz, nants, axis=0).reshape((nants, nants, 3))
        uvw = np.zeros((nants*nants, 3))
        uvw[:,0] = (repxyz[:,:,0] - repxyz[:,:,0].T).flatten()
        uvw[:,1] = (repxyz[:,:,1] - repxyz[:,:,1].T).flatten()
        uvw[:,2] = (repxyz[:,:,2] - repxyz[:,:,2].T).flatten()

        #split up polarizations
        xxVis = corrMatrix[0::2,0::2].reshape(nants*nants)
        xyVis = corrMatrix[0::2,1::2].reshape(nants*nants)
        yxVis = corrMatrix[1::2,0::2].reshape(nants*nants)
        yyVis = corrMatrix[1::2,1::2].reshape(nants*nants)

        ##uv coverage plot
        #plt.plot(uvw[:,0], uvw[:,1], '.')
        #plt.show()

    #TODO: MS
    #elif fDict['fmt']=='ms': #MS-based visibilities

    #    fDict['sb'] = int(opts.subband)

    #    MS = pt.table(visFile, readonly=True)
    #    data_column = opts.column.upper()
    #    uvw = MS.col('UVW').getcol() # [vis id, (u,v,w)]
    #    vis = MS.col(data_column).getcol() #[vis id, freq id, stokes id]
    #    #print vis.shape
    #    #print uvw.shape
    #    vis = vis[:,fDict['sb'],:] #select a single subband
    #    MS.close()

    #    #freq information, convert uvw coordinates
    #    SW = pt.table(visFile + '/SPECTRAL_WINDOW')
    #    freqs = SW.col('CHAN_FREQ').getcol() # [1, nchan]
    #    uvw = uvw*freqs[0,fDict['sb']]/cc #convert (u,v,w) from metres to wavelengths
    #    print 'SUBBAND: %i (%f MHz)'%(fDict['sb'], freqs[0,fDict['sb']]/1e6)
    #    SW.close()

    #    ##uv coverage plot
    #    #plt.plot(uvw[:,0], uvw[:,1], '.')
    #    #plt.show()

    #    #split up polarizations
    #    xxVis = vis[:,0] 
    #    xyVis = vis[:,1]
    #    yxVis = vis[:,2]
    #    yyVis = vis[:,3]

    else:
        print 'ERROR: unknown data format, exiting'
        exit()
    
    #remove auto-correlations
    print 'AUTO-CORRELATIONS:', opts.autos
    if not opts.autos:
        autoIdx = np.argwhere(uvw[:,0]**2. + uvw[:,1]**2. + uvw[:,2]**2. == 0.)
        xxVis[autoIdx] = 0.
        xyVis[autoIdx] = 0.
        yxVis[autoIdx] = 0.
        yyVis[autoIdx] = 0.

    #prepare for SWHT
    print 'Performing Spherical Wave Harmonic Transform'
    print 'LMAX:', opts.lmax
    #TODO: only doing total intensity right now
    iImgCoeffs = SWHT.swht.swhtImageCoeffs(xxVis+yyVis, uvw, np.array([freq]), lmax=opts.lmax)

    #save image coefficients to file
    if opts.ocoeffs is None: outCoeffPklFn = 'tempCoeffs.pkl'
    else: outCoeffPklFn = opts.pkl
    SWHT.fileio.writeCoeffPkl(outCoeffPklFn, iImgCoeffs)

    #iImgCoeffs = np.ones((7, 13, 1))

    #print iImgCoeffs.shape
    #print iImgCoeffs[:,:,0]
    #temp = np.hstack((iImgCoeffs[:,:,0].real, iImgCoeffs.imag[:,:,0]))
    #temp[0,0] = 0.
    #plt.imshow(temp, interpolation='nearest')
    #plt.colorbar()
    #plt.show()
    #exit()

    #TODO: make image
    #img = SWHT.swht.make2Dimage(iImgCoeffs, dim=[64, 64])
    #plt.imshow(np.abs(img), interpolation='nearest')
    #plt.colorbar()
    #plt.show()

    img = SWHT.swht.make3Dimage(iImgCoeffs, dim=[128, 128])
    img = np.abs(img)
    #[theta, phi] = np.meshgrid(np.linspace(0, np.pi, num=128, endpoint=False), np.linspace(0, 2.*np.pi, num=128, endpoint=False))
    [theta, phi] = np.meshgrid(np.linspace(0, np.pi, num=128, endpoint=True), np.linspace(0, 2.*np.pi, num=128, endpoint=True))
    #http://stackoverflow.com/questions/22175533/what-is-the-equivalent-of-matlabs-surfx-y-z-c-in-matplotlib
    from mpl_toolkits.mplot3d import Axes3D
    from matplotlib import cm
    from matplotlib.colors import Normalize
    fig = plt.figure()
    ax = fig.gca(projection='3d')
    #X = np.cos(theta-(np.pi/2.)) * np.cos(phi)
    #Y = np.cos(theta-(np.pi/2.)) * np.sin(phi)
    #Z = np.sin(theta-(np.pi/2.))
    X, Y, Z = SWHT.util.sph2cart(theta, phi)

    imin = img.min()
    imax = img.max()
    scalarMap = cm.ScalarMappable(norm=Normalize(vmin=imin, vmax=imax), cmap=cm.jet)
    C = scalarMap.to_rgba(img)

    #surf = ax.plot_surface(X, -1.*Y, -1.*Z, rstride=1, cstride=1, facecolors=C, antialiased=True)
    surf = ax.plot_surface(X, Y, -1.*Z, rstride=1, cstride=1, facecolors=C, antialiased=True)
    plt.show()

    ##save complex image to pickle file
    #if opts.pkl is None: outPklFn = 'tempImage.pkl'
    #else: outPklFn = opts.pkl
    #if opts.dft: fttype = 'dft'
    #else: fttype = opts.conv
    #print 'Writing image to file %s ...'%outPklFn,
    #SWHT.fileio.writeImgPkl(outPklFn, np.array([xxIm,xyIm,yxIm,yyIm]), fDict, res=res, fttype=fttype, imtype='complex')
    #print 'done'
    #
    ##display stokes plots
    #if not opts.nodisplay or not (opts.savefig is None):
    #    #generate stokes images
    #    iIm = (xxIm + yyIm).real
    #    qIm = (xxIm - yyIm).real
    #    uIm = (xyIm + yxIm).real
    #    vIm = (yxIm - xyIm).imag
    #
    #    plt.subplot(2,2,1)
    #    plt.imshow(iIm)
    #    plt.xlabel('Pixels (E-W)')
    #    plt.ylabel('Pixels (N-S)')
    #    plt.title('I')
    #    plt.colorbar()
    #    plt.subplot(2,2,2)
    #    plt.imshow(qIm)
    #    plt.xlabel('Pixels (E-W)')
    #    plt.ylabel('Pixels (N-S)')
    #    plt.title('Q')
    #    plt.colorbar()
    #    plt.subplot(2,2,3)
    #    plt.imshow(uIm)
    #    plt.xlabel('Pixels (E-W)')
    #    plt.ylabel('Pixels (N-S)')
    #    plt.title('U')
    #    plt.colorbar()
    #    plt.subplot(2,2,4)
    #    plt.imshow(vIm)
    #    plt.xlabel('Pixels (E-W)')
    #    plt.ylabel('Pixels (N-S)')
    #    plt.title('V')
    #    plt.colorbar()
    #if not (opts.savefig is None): plt.savefig(opts.savefig)
    #if not opts.nodisplay: plt.show()
