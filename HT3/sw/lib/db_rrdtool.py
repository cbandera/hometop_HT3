#! /usr/bin/python3
#
#################################################################
## Copyright (c) 2013 Norbert S. <junky-zs@gmx.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#################################################################
# Ver:0.1.5  / Datum 25.05.2014
#################################################################
#
""" Class 'cdb_rrdtool' for creating and writing data to rrdtool-database

cdb_rrdtool.__init__    -- constructor of class 'cdb_rrdtool'
                             mandatory: parameter 'configurationfilename' (Path and name)
                             optional : PerlIF (default must be set to 'True')
                                        perl is used to handle the interface to rrdtool
createdb_rrdtool        -- creating database 'rrdtool'
                             The db-structur is taken from xml-configurefile
                             mandatory: Perl 'RRDTool::OO' is installed
                             optional : timestamp    (default is value from configuration)
                                        step_seconds (default is value from configuration)
db_rrdtool_filename     -- return of used rrdtool-db  filename.
                             mandatory: none
syspartnames            -- returns the 'syspartnames' from configuration as directory
                             structur : {shortname:syspartname}
                             mandatory: none
dbfilenames             -- returns the 'database-filenames' from configuration as:
                             1. directory     <- 'syspartname' := None
                             2. folder-string <- 'syspartname' := valid nickname e.g. 'HK'
                             structur : {shortname:Filename}
                             mandatory: none
                             optional : Syspartshortname (default is 'None')
isavailable             -- returns True/False if database is available/not available
                             mandatory: none
update                  -- updates the rrdtool-database entry 'syspartname' with value(s)
                             mandatory: syspartname <- syspart-longname (not nickname!)
                                        values      <- array of tuples [(n1,v1),(n2,v2),...]
                             optional : timestamp        (default is current UTC-time) 
is_rrdtool_db_available -- returns True/False on status rrdtool-db available/not available
                             mandatory: none
                             optional : db-name      (default is value from configuration)
is_rrdtool_db_enabled   -- returns True/False for rrdtool-db config-tag 'enable'
db_rrdtool_stepseconds  -- returns value 'step_seconds' for rrdtool-db
db_rrdtool_starttime_utc-- returns value 'starttime_utc' for rrdtool-db
                             
"""

import os, tempfile
import xml.etree.ElementTree as ET
import time


class cdb_rrdtool(object):
    __rrdtool_syspartnames   ={}
    __rrdtool_dbname_mapping ={}
    def __init__(self, configurationfilename, PerlIF=True):
        self.__databasefiles=[]
        self.__rrdtoolh=None   #used as rrdtool-handle
        self.__rrdfileh=None
        self.__rrdtool_enable=False
        self.__rrdtool_stepseconds=60
        self.__rrdtool_starttime_utc=0
        
        # flag used to activate perl rrdtool-handling,
        #  it is not yet available for Python3 and debian
        self.__PerlIF=PerlIF
        try:
            if not isinstance(configurationfilename, str):
                raise TypeError("Parameter: configurationfilename")
            
            #get database-name from configuration
            tree  = ET.parse(configurationfilename)
            self.__root  = tree.getroot()
            self.__dbname=self.__root.find('dbname_rrd').text
            if not len(self.__dbname):
                raise NameError("'dbname_rrd' not found in configuration")
            
            self.__path    = os.path.dirname (self.__dbname)
            self.__basename= os.path.basename(self.__dbname)
            if not os.path.isabs(self.__dbname):
                abspath=os.path.abspath(".")
                self.__fullpathname=os.path.join(abspath,os.path.abspath(self.__dbname))
            else:
                self.__fullpathname=self.__dbname

            self.__Perl_dbcreateFile=os.path.normcase("/tmp/rrdtool_dbcreate.pl")
            self.__fillup_mapping()

            for rrdtool_part in self.__root.findall('rrdtool-db'):
                self.__rrdtool_enable    =rrdtool_part.find('enable').text.upper()
                if self.__rrdtool_enable=='ON' or self.__rrdtool_enable=='1':
                    self.__rrdtool_enable=True
                else:
                    self.__rrdtool_enable=False
                    
                self.__rrdtool_stepseconds  =int(rrdtool_part.find('step_seconds').text)
                if self.__rrdtool_stepseconds < 60:
                    self.__rrdtool_stepseconds=60
                    
                self.__rrdtool_starttime_utc=int(rrdtool_part.find('starttime_utc').text)
                if self.__rrdtool_starttime_utc<1344000000 or self.__rrdtool_starttime_utc>1999999999:
                    self.__rrdtool_starttime_utc=1344000000

        except (OSError, EnvironmentError, TypeError, NameError) as e:
            print("""cdb_rrdtool();Error;<{0}>""".format(str(e.args)))
            raise e
            
    def __del__(self):
        pass

    def __fillup_mapping(self):
        for syspart in self.__root.findall('systempart'):
            syspartname    = syspart.attrib["name"]
            shortnameinpart= syspart.find('shortname')
            shortname      = shortnameinpart.attrib["name"]
            Filename=self.__fullpathname+"_"+str(syspartname)+".rrd"
            cdb_rrdtool.__rrdtool_syspartnames.update({shortname:syspartname})
            cdb_rrdtool.__rrdtool_dbname_mapping.update({shortname:Filename})

    def syspartnames(self):
        return cdb_rrdtool.__rrdtool_syspartnames

    def dbfilenames(self, syspartname=None):
        if not syspartname==None:
            return cdb_rrdtool.__rrdtool_dbname_mapping[syspartname]
        else:
            return cdb_rrdtool.__rrdtool_dbname_mapping
        
        
    def isavailable(self):
        #find database-files in directory
        dircontent=os.listdir(self.__path)
        filefound = 0
        for content in dircontent:
            if self.__basename in content:
                self.__databasefiles.append(content)
                filefound+=1

        return bool(filefound)        

    def update(self, syspartname, values, timestamp=None):
        rtn=0
        try:
            if not self.isavailable(): raise EnvironmentError("database not yet created")
            
            if timestamp==None:
                itimestamp=int(time.time())
            else:
                itimestamp=int(timestamp)
            rrdfile  = tempfile.NamedTemporaryFile()
            filename = rrdfile.name+"_"+syspartname+".pl"
            self.__rrdfileh=open("{0}".format(filename), "w")
            self.__define_rrd_update_fileheader()
            self.__define_rrd_update_filehandle(syspartname, itimestamp)
            self.__define_rrd_update_details(syspartname, values)
            self.__rrdfileh.close()
            
            #setup executemode for file to: 'rwxr-xr-x'
            os.chmod(filename, 0o755)
            #execute perl-script for updating 'rrdtool' database
            error=os.system(filename)
            if error:
                self.__rrdfileh=open("{0}".format(filename), "a")
                self.__rrdfileh.write('# ---- error occured: -------\n')
                self.__rrdfileh.write('# {0}, syspart:{1}, timestamp:{2}\n'.format(error,
                                                                                   syspartname,
                                                                                   itimestamp))
                self.__rrdfileh.flush()
                self.__rrdfileh.close()
                raise ValueError("""script failed, syspart:{0}, timestamp:{1}""".format(syspartname,
                                                                                        itimestamp))
            else:
                os.remove(filename)

            return bool(error)
            
        except (ValueError, EnvironmentError, NameError, TypeError) as e:
            if not self.__rrdfileh==None: self.__rrdfileh.close()
            print('cdb_rrdtool.update();Error;<{0}>'.format(e.args[0]))
            return True

    def __define_rrd_update_fileheader(self):
        try:
            self.__rrdfileh.write("#!/usr/bin/perl\n#\nuse strict;\nuse warnings;\nuse RRDTool::OO;\n\n")
            self.__rrdfileh.flush()                                          
        except (EnvironmentError) as e:
            print('cdb_rrdtool.update();Error;<{0}>'.format(e.args[0]))
            raise e

    def __define_rrd_update_filehandle(self,syspartname, timestamp):
        try:
            Filename=self.__fullpathname+"_"+str(syspartname)+".rrd"
            self.__rrdfileh.write('my $DB_{0}  = "{1}";\n'.format(syspartname,Filename))
            self.__rrdfileh.write('my ${0}_rrdh = RRDTool::OO->new(file => $DB_{0});\n'.format(syspartname))
            self.__rrdfileh.write('#\n')
            self.__rrdfileh.write('${0}_rrdh->update (\n'.format(syspartname))
            self.__rrdfileh.write('  time   => {0},\n'.format(timestamp))
            self.__rrdfileh.write('  values => {\n')
            self.__rrdfileh.flush()                                          
        except (EnvironmentError) as e:
            print('cdb_rrdtool.update();Error;<{0}>'.format(e.args[0]))
            raise e

    def __define_rrd_update_details(self, syspartname, values):
        try:
            if not (isinstance(values, list) and isinstance(values[0], tuple)):
                raise TypeError("only a list of tuples allowed for 'values'")
            for (logitem, value) in values:
                if len(str(logitem)) > 18: raise TypeError("logitem-length must be less then 19 chars")
                self.__rrdfileh.write('   {0}=>{1},\n'.format(logitem, value))
            self.__rrdfileh.write('   }\n')
            self.__rrdfileh.write(');\n')
            self.__rrdfileh.flush()                                          
                
        except (EnvironmentError) as e:
            print('cdb_rrdtool.update();Error;<{0}>'.format(e.args[0]))
            raise e

    
    def createdb_rrdtool(self, timestamp=None, step_seconds=None):
        if self.is_rrdtool_db_available():
            print("cdb_rrdtool.createdb_rrdtool();INFO;Database:'{0}' already created".format(self.__dbname))
        else:
            if not self.__PerlIF:
               raise EnvironmentError("rrdtool database-creation is done with perl-scripts")
            try:
                # set starttime and step-seconds for rrdtool-db
                if timestamp==None:
                    itimestamp=int(self.__rrdtool_starttime_utc)
                else:
                    itimestamp=int(timestamp)

                if step_seconds==None:
                    istep_seconds=int(self.__rrdtool_stepseconds)
                else:
                    istep_seconds=int(step_seconds)
                    
                #create file to fillup this as perlscript with dbcreate-informations
                self.__rrdtoolh=open("{0}".format(self.__Perl_dbcreateFile), "w")
                # first fillup fileheader
                self.__define_rrd_fileheader()

                # then fillup filehandles
                for syspart in self.__root.findall('systempart'):
                    syspartname = syspart.attrib["name"]
                    self.__define_rrd_filehandle(syspartname)

                # then fillup startuptime and step-seconds
                self.__define_rrd_starttime(itimestamp, istep_seconds)
                
                for syspart in self.__root.findall('systempart'):
                    syspartname = syspart.attrib["name"]
                    #write detail-header
                    self.__define_rrd_details(syspartname, "","","",True)
                    
                    for logitem in syspart.findall('logitem'):
                        name = logitem.attrib["name"]
                        datause = logitem.find('datause').text.upper()
                        maxvalue= logitem.find('maxvalue').text
                        default = logitem.find('default').text
                        if datause in ['GAUGE','COUNTER','DERIVE','ABSOLUTE','COMPUTE']:
                            # fillup database-details for logitems
                            self.__define_rrd_details(syspartname,name,datause,default)
                    #write trailer
                    self.__define_rrd_details(syspartname, "","","",False,True)
                self.__rrdtoolh.close()

                #setup executemode for file to: 'rwxr-xr-x'
                os.chmod(self.__Perl_dbcreateFile, 0o755)
                
                #execute perl-script to create 'rrdtool' database
                os.system(self.__Perl_dbcreateFile)

                #check rrdtool-db for availability, if not raise exception
                if not self.is_rrdtool_db_available():
                   raise EnvironmentError("rrdtool-database:'{0}' not created".format(self.__dbname))
            
            except (EnvironmentError, TypeError) as e:
                if not self.__rrdtoolh==None: self.__rrdtoolh.close()
                print('db_rrdtool.createdb_rrdtool();Error;<{0}>'.format(e.args[0]))

    def __define_rrd_fileheader(self):
        try:
            self.__rrdtoolh.write("#!/usr/bin/perl\n#\nuse strict;\nuse warnings;\nuse RRDTool::OO;\n\n")
            self.__rrdtoolh.write('my $rc = 0;\n')
            self.__rrdtoolh.flush()                                          
        except (EnvironmentError) as e:
            print('db_rrdtool.createdb_rrdtool();Error;<{0}>'.format(e.args[0]))
            raise e

    def __define_rrd_filehandle(self,syspartname):
        try:
            Filename=self.__fullpathname+"_"+str(syspartname)+".rrd"
            self.__rrdtoolh.write('my $DB_{0}  = "{1}";\n'.format(syspartname,Filename))
            self.__rrdtoolh.write('my ${0}_rrdh = RRDTool::OO->new(file => $DB_{0});\n'.format(syspartname))
            self.__rrdtoolh.flush()                                          
        except (EnvironmentError) as e:
            print('db_rrdtool.createdb_rrdtool();Error;<{0}>'.format(e.args[0]))
            raise e

    def __define_rrd_starttime(self, starttime=None, iterations="100"):
        try:
            if starttime==None:
                istarttime=int(time.time())
            else:
                istarttime=int(starttime)
                          
            self.__rrdtoolh.write('# \n')
            self.__rrdtoolh.write('# Set Starttime\n')
            self.__rrdtoolh.write('my $start_time     = {0};\n'.format(istarttime))
            self.__rrdtoolh.write('my $step           = {0};\n'.format(iterations))
            self.__rrdtoolh.write('# \n')
            self.__rrdtoolh.write('# Define the RRD\n')
            self.__rrdtoolh.write("# RRA's consolidation function must be one of the following:\n")
            self.__rrdtoolh.write("#  ['AVERAGE', 'MIN', 'MAX', 'LAST', 'HWPREDICT', 'SEASONAL',\n")
            self.__rrdtoolh.write("#   'DEVSEASONAL', 'DEVPREDICT', 'FAILURES']\n")
            self.__rrdtoolh.write('# \n')
            self.__rrdtoolh.write("# Define the archiv\n")
            self.__rrdtoolh.write("# 'LAST    saved every 5 min, kept for 10years back\n")
            self.__rrdtoolh.write("# 'AVERAGE saved every 1 min, kept for  1year  back\n")
            self.__rrdtoolh.write("# 'MAX  saved every 5 min, kept for 1year back\n")
            self.__rrdtoolh.write("# 'MIN  saved every 5 min, kept for 1year back\n")
            self.__rrdtoolh.write('# \n')
            self.__rrdtoolh.flush()                                          
        except (EnvironmentError) as e:
            print('db_rrdtool.createdb_rrdtool();Error;<{0}>'.format(e.args[0]))
            raise e

    def __define_rrd_details(self,syspartname, logitem, datause, default, heading=False, tail=False):
        try:
            if heading:
                rrd_handlename=syspartname+"_rrdh"
                self.__rrdtoolh.write('$rc = ${0}->create(\n'.format(rrd_handlename))
                self.__rrdtoolh.write('    start       => $start_time - 600,\n')
                self.__rrdtoolh.write('    step        => $step,\n')
            elif tail:
                self.__rrdtoolh.write('        archive     => { \n')
                self.__rrdtoolh.write('            rows     => 1051200,\n')
                self.__rrdtoolh.write('            cpoints  => 5,\n')
                self.__rrdtoolh.write("            cfunc    => 'LAST',\n")
                self.__rrdtoolh.write('        },\n')
                self.__rrdtoolh.write('        archive     => { \n')
                self.__rrdtoolh.write('            rows     => 525600,\n')
                self.__rrdtoolh.write('            cpoints  => 1,\n')
                self.__rrdtoolh.write("            cfunc    => 'AVERAGE',\n")
                self.__rrdtoolh.write('        },\n')
                self.__rrdtoolh.write('        archive     => { \n')
                self.__rrdtoolh.write('            rows     => 105120,\n')
                self.__rrdtoolh.write('            cpoints  => 5,\n')
                self.__rrdtoolh.write("            cfunc    => 'MAX',\n")
                self.__rrdtoolh.write('        },\n')
                self.__rrdtoolh.write('        archive     => { \n')
                self.__rrdtoolh.write('            rows     => 105120,\n')
                self.__rrdtoolh.write('            cpoints  => 5,\n')
                self.__rrdtoolh.write("            cfunc    => 'MIN',\n")
                self.__rrdtoolh.write('        }\n')
                self.__rrdtoolh.write(');\n')
                self.__rrdtoolh.flush()                                          
            else:
                self.__rrdtoolh.write('        data_source => { \n')
                self.__rrdtoolh.write("            name    => '{0}',\n".format(logitem))
                self.__rrdtoolh.write("            type    => '{0}',\n".format(datause))
                self.__rrdtoolh.write("        },\n")

            self.__rrdtoolh.flush()                                          
        except (EnvironmentError) as e:
            self.__rrdtoolh.flush()                                          
            print('db_rrdtool.createdb_rrdtool();Error;<{0}>'.format(e.args[0]))
            raise e

    def is_rrdtool_db_available(self, dbname=""):
        syspartname=""
        syspartcount=0
        dbfilescount=0
        rtnvalue=False
        try:
            if len(dbname):
                # check the file 'dbname' with it's naming for availability
                if os.access(dbname,os.W_OK and os.R_OK):
                    rtnvalue=True
            else:
                for syspart in self.__root.findall('systempart'):
                        syspartname = syspart.attrib["name"]
                        Filename=self.__dbname+"_"+str(syspartname)+".rrd"
                        #check of dbfile-available
                        if os.access(Filename,os.W_OK and os.R_OK):
                            dbfilescount+=1
                        syspartcount+=1
                if dbfilescount>0 and dbfilescount==syspartcount:
                    rtnvalue=True

            return rtnvalue
        except (EnvironmentError) as e:
            print('create_db.__is_rrdtool_db_available();Error;<{0}>'.format(e.args[0]))
            return False

    def db_rrdtool_filename(self):
        # returns the db-basename
        return self.__dbname
        
    def is_rrdtool_db_enabled(self):
        return self.__rrdtool_enable
    
    def db_rrdtool_stepseconds(self):
        return self.__rrdtool_stepseconds

    def db_rrdtool_starttime_utc(self):
        return self.__rrdtool_starttime_utc
    
        
#--- class cdb_rrdtool end ---#

### Runs only for test ###########
if __name__ == "__main__":
    configurationfilename='./../etc/config/4test/create_db_test.xml'
    db_rrdtool=cdb_rrdtool(configurationfilename)
    print("------------------------")
    print("Config: get rrdtool-database configuration at first")
    print("configfile            :'{0}'".format(configurationfilename))
    print("rrdtool db-file       :'{0}'".format(db_rrdtool.db_rrdtool_filename()))
    print("rrdtool db_enabled    :{0}".format(db_rrdtool.is_rrdtool_db_enabled()))
    print("rrdtool db_stepseconds:{0}".format(db_rrdtool.db_rrdtool_stepseconds()))
    print("rrdtool db_starttime  :{0}".format(db_rrdtool.db_rrdtool_starttime_utc()))
    
    print("------------------------")
    print("Create: rrdtool-database next (independent from 'db_enabled' flag)")
    db_rrdtool.createdb_rrdtool()
    
    print("------------------------")
    print("Update: rrdtool-database")
    values=[("T_ist_HK",22.3),("T_soll_HK",21.0)]
    error=db_rrdtool.update("heizkreis1",values)
    if error:
        print("Update rrdtool database Failed")
    else:
        print("Update rrdtool database OK")
    for syspartshortname in db_rrdtool.syspartnames():
        syspart=db_rrdtool.syspartnames()[syspartshortname]
        print("Shortname: {0:2}, syspartname: {1}\n +-> rrdtool_file: {2}\n".format(syspartshortname,
                                                                                syspart,
                                                                                db_rrdtool.dbfilenames()[syspartshortname]))