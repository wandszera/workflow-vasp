#!/bin/bash
#SBATCH --job-name=DFT-VASP_p
#SBATCH --mem=32000
#SBATCH --nodes=1
#SBATCH --tasks-per-node=32
#SBATCH --partition=simstack
#SBATCH --error=my_vasp.stderr
#SBATCH --output=my_vasp.stdout
#SBATCH --time=120:00:00

module purge
module load intel/19.0.5.281
#module load vasp prun

#go to exec dir here
srun --mpi=pmi2 /home/ws/op2044/VASP/vasp.5.4.4.pl2/bin/vasp_std
#prun vasp_std
